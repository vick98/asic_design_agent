// fsdbq.cpp — FFR (FSDB File Reader) 波形查询小工具
// ---------------------------------------------------------------------------
// 依赖：仅 Verdi 自带的 libnffr.so / libnsys.so + libz
//      —— 不需要 Verdi 主程序、不需要 License、不需要 X server。
//
// 为什么必须是 C++：libnffr.so 导出的是 C++ mangled 符号（_ZN9ffrObject...），
// ctypes / extern "C" 无法直接调用，只能包一层薄壳。
//
// 输出协议：stdout 逐行 `<REC>\t<field>...`，REC 为单字母记录类型。
//   FFR 自身会往 stdout 打杂项行（如 "logDir = /tmp/"），调用方按 REC
//   白名单过滤即可。诊断信息一律走 stderr。
//
// 记录类型：
//   I  key value                                文件元信息
//   V  hier idcode l r vtype dir                变量
//   S  hier depth                               层次
//   C  hier period cv nedges nrising            选定时钟
//   R  time                                     时钟上升沿
//   F  time                                     时钟下降沿
//   B  idx requested resolved idcode l r        波形信号解析结果
//   N  idx requested                            信号未找到
//   P  idx time value                           窗口起点前的种子值
//   W  idx time value                           值变
//   E  idx count truncated                      值变统计
//   Z  key value                                汇总
// ---------------------------------------------------------------------------

#include "ffrAPI.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

// ffrAPI.h 用了 bool_T/TRUE/FALSE 但没有把 TRUE/FALSE 定义给我（原型同样手工补）
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

// ------------------------------------------------------------------ helpers

static std::string lower(const std::string &s) {
  std::string r(s);
  for (size_t i = 0; i < r.size(); ++i)
    r[i] = (char)tolower((unsigned char)r[i]);
  return r;
}

static bool has_substr_ci(const std::string &hay, const std::string &needle) {
  if (needle.empty()) return true;
  return lower(hay).find(lower(needle)) != std::string::npos;
}

static bool has_prefix(const std::string &s, const std::string &p) {
  return s.size() >= p.size() && s.compare(0, p.size(), p) == 0;
}

static std::string chomp(const std::string &s) {
  size_t e = s.size();
  while (e > 0 && (s[e - 1] == '\n' || s[e - 1] == '\r' || s[e - 1] == ' ' ||
                   s[e - 1] == '\t'))
    --e;
  return s.substr(0, e);
}

// FFR 的 var name 带位宽后缀（reg_counter[3:0]），VCD/NPI 用裸名。
static std::string bare_name(const char *nm) {
  std::string s = nm ? nm : "";
  size_t p = s.find('[');
  if (p != std::string::npos) s = s.substr(0, p);
  return s;
}

static const char *vtype_name(int t) {
  switch (t & 0x3f) {  // 去掉 FSDB_VT_MIDDLE(64) / FSDB_VT_COMPUTED(128) 标记位
    case FSDB_VT_VCD_EVENT:        return "event";
    case FSDB_VT_VCD_INTEGER:      return "integer";
    case FSDB_VT_VCD_PARAMETER:    return "parameter";
    case FSDB_VT_VCD_REAL:         return "real";
    case FSDB_VT_VCD_REG:          return "reg";
    case FSDB_VT_VCD_SUPPLY0:      return "supply0";
    case FSDB_VT_VCD_SUPPLY1:      return "supply1";
    case FSDB_VT_VCD_TIME:         return "time";
    case FSDB_VT_VCD_TRI:          return "tri";
    case FSDB_VT_VCD_TRIAND:       return "triand";
    case FSDB_VT_VCD_TRIOR:        return "trior";
    case FSDB_VT_VCD_TRIREG:       return "trireg";
    case FSDB_VT_VCD_TRI0:         return "tri0";
    case FSDB_VT_VCD_TRI1:         return "tri1";
    case FSDB_VT_VCD_WAND:         return "wand";
    case FSDB_VT_VCD_WIRE:         return "wire";
    case FSDB_VT_VCD_WOR:          return "wor";
    case FSDB_VT_VCD_MEMORY:       return "memory";
    case FSDB_VT_VCD_PORT:         return "port";
    case 20:                       return "reg";
    case 21:                       return "wire";   // FSDB_VT_VCD_PACKED
    case 22:                       return "wire";   // FSDB_VT_VCD_PACKED_ENUM
    case 25:                       return "wire";   // FSDB_VT_SV_VARIABLE
    case 32:                       return "signal"; // FSDB_VT_VHDL_SIGNAL
    case 33:                       return "variable";
    case 34:                       return "constant";
    default:                       return "wire";
  }
}

static unsigned long long tag2ull(const fsdbTag64 *t) {
  return ((unsigned long long)t->H << 32) | (unsigned long long)t->L;
}

static void ull2tag(fsdbTag64 *t, unsigned long long v) {
  t->H = (uint_T)(v >> 32);
  t->L = (uint_T)(v & 0xffffffffULL);
}

// ------------------------------------------------------------------ var tree

struct VarRec {
  std::string hier;
  std::string name;
  int l;
  int r;
  int vtype;
  int dir;
  fsdbVarIdcode id;
};

struct ScopeRec {
  std::string hier;
  int depth;
};

struct Collector {
  std::vector<VarRec> vars;
  std::vector<ScopeRec> scopes;
  std::vector<std::string> stack;
};

static std::string join_stack(const std::vector<std::string> &st) {
  std::string out;
  for (size_t i = 0; i < st.size(); ++i) {
    if (i) out += ".";
    out += st[i];
  }
  return out;
}

static bool_T tree_cb(fsdbTreeCBType t, void *cd, void *data) {
  Collector *C = (Collector *)cd;
  switch (t) {
    case FSDB_TREE_CBT_SCOPE: {
      fsdbTreeCBDataScope *s = (fsdbTreeCBDataScope *)data;
      C->stack.push_back(s->name ? s->name : "");
      ScopeRec sr;
      sr.hier = join_stack(C->stack);
      sr.depth = (int)C->stack.size();
      C->scopes.push_back(sr);
      break;
    }
    case FSDB_TREE_CBT_UPSCOPE:
      if (!C->stack.empty()) C->stack.pop_back();
      break;
    case FSDB_TREE_CBT_VAR: {
      fsdbTreeCBDataVar *v = (fsdbTreeCBDataVar *)data;
      VarRec r;
      r.name = bare_name(v->name);
      std::string sc = join_stack(C->stack);
      r.hier = sc.empty() ? r.name : (sc + "." + r.name);
      r.l = v->lbitnum;
      r.r = v->rbitnum;
      r.vtype = (int)v->type;
      // real 信号：FFR 的 lbitnum/rbitnum 恒为 0，按原样会让我们误判成 1 bit
      // （进而走单 bit 波形字符，把实数值变成 x）。VCD 里是 `$var real 64`，
      // 故统一成 63/0 -> width 64，与旧工具 aic_tool_trace 的判定一致。
      if (((int)v->type & 0x3f) == FSDB_VT_VCD_REAL ||
          v->bytes_per_bit == FSDB_BYTES_PER_BIT_8B) {
        r.l = 63;
        r.r = 0;
      }
      r.dir = (int)v->direction;
      r.id = (fsdbVarIdcode)v->u.idcode;
      C->vars.push_back(r);
      break;
    }
    default:
      break;
  }
  return TRUE;
}

// name_index: 叶子名 -> 变量下标，按层次深度升序（与 VCDParser 一致）
struct VarIndex {
  std::map<std::string, int> hier_index;
  std::map<std::string, std::vector<int> > name_index;

  void build(const std::vector<VarRec> &vars) {
    hier_index.clear();
    name_index.clear();
    for (size_t i = 0; i < vars.size(); ++i) {
      if (hier_index.find(vars[i].hier) == hier_index.end())
        hier_index[vars[i].hier] = (int)i;
      name_index[vars[i].name].push_back((int)i);
    }
    for (std::map<std::string, std::vector<int> >::iterator it = name_index.begin();
         it != name_index.end(); ++it) {
      std::vector<int> &v = it->second;
      for (size_t a = 1; a < v.size(); ++a) {  // 按 "." 个数做稳定插入排序
        int key = v[a];
        int kd = depth_of(vars[key]);
        size_t b = a;
        while (b > 0 && depth_of(vars[v[b - 1]]) > kd) {
          v[b] = v[b - 1];
          --b;
        }
        v[b] = key;
      }
    }
  }

  static int depth_of(const VarRec &r) {
    int n = 0;
    for (size_t i = 0; i < r.hier.size(); ++i)
      if (r.hier[i] == '.') ++n;
    return n;
  }

  // exact -> 命中层次全名；否则 -> 同名叶子中层次最浅者
  const VarRec *resolve(const std::vector<VarRec> &vars, const std::string &path,
                        bool *is_exact) const {
    std::map<std::string, int>::const_iterator hit = hier_index.find(path);
    if (hit != hier_index.end()) {
      if (is_exact) *is_exact = true;
      return &vars[hit->second];
    }
    std::string leaf = path;
    size_t dot = path.rfind('.');
    if (dot != std::string::npos) leaf = path.substr(dot + 1);
    std::map<std::string, std::vector<int> >::const_iterator nit =
        name_index.find(leaf);
    if (nit != name_index.end() && !nit->second.empty()) {
      if (is_exact) *is_exact = false;
      return &vars[nit->second[0]];
    }
    return NULL;
  }
};

// ------------------------------------------------------------------ VC dumps

// 把 FFR 的原始 VC 转成 VCDParser 的值表示法：
//   1 bit  -> "0"/"1"/"x"/"z"
//   多 bit -> "b0101"（小写）
//   real   -> "r3.14"
static bool vc_to_string(ffrVCTrvsHdl h, std::string *out) {
  byte_T *vc = NULL;
  if (h->ffrGetVC(&vc) != FSDB_RC_SUCCESS || vc == NULL) return false;

  fsdbBytesPerBit bpb = h->ffrGetBytesPerBit();
  if (bpb == FSDB_BYTES_PER_BIT_1B) {
    uint_T bits = h->ffrGetBitSize();
    if (bits == 0) bits = 1;
    if (bits > FSDB_MAX_BIT_SIZE) bits = FSDB_MAX_BIT_SIZE;
    std::string s;
    s.reserve(bits + 1);
    for (uint_T i = 0; i < bits; ++i) {
      switch (vc[i]) {
        case FSDB_BT_VCD_0: s += '0'; break;
        case FSDB_BT_VCD_1: s += '1'; break;
        case FSDB_BT_VCD_Z: s += 'z'; break;
        case FSDB_BT_VCD_X:
        default:            s += 'x'; break;
      }
    }
    *out = (bits == 1) ? s : ("b" + s);
    return true;
  }
  if (bpb == FSDB_BYTES_PER_BIT_8B) {
    double d;
    memcpy(&d, vc, sizeof(double));
    char buf[64];
    // 复刻 VCS 写 VCD 实数的方式（%.16f 加一个尾随空格：VCD 原文是
    // `r0.1000000000000000  <id>`，解析后值保留数字后的那个空格），
    // 以保证与旧工具 aic_tool_trace 的输出逐字节一致。
    snprintf(buf, sizeof(buf), "%.16f ", d);
    *out = std::string("r") + buf;
    return true;
  }
  float f;
  memcpy(&f, vc, sizeof(float));
  char buf[64];
  snprintf(buf, sizeof(buf), "%.16f ", (double)f);
  *out = std::string("r") + buf;
  return true;
}

// 遍历一个信号的全部值变；[from, to] 内通过 out 回调逐条给出。
// seed 给出「时间 <= from 的最后一次值变」（可能为空）。
struct VCWalker {
  std::vector<unsigned long long> times;
  std::vector<std::string> values;
  bool has_seed;
  unsigned long long seed_time;
  std::string seed_value;
  unsigned long long total;   // 全时间段值变总数（不受窗口限制）
};

static bool walk_vc(ffrObject *obj, fsdbVarIdcode id, unsigned long long from,
                    unsigned long long to, long long max_changes,
                    VCWalker *out) {
  out->has_seed = false;
  out->seed_time = 0;
  out->seed_value.clear();
  out->total = 0;

  ffrVCTrvsHdl h = obj->ffrCreateVCTrvsHdl(id);
  if (!h) return false;
  if (FALSE == h->ffrHasIncoreVC()) {
    h->ffrFree();
    return true;
  }

  fsdbTag64 tag;
  h->ffrGetMinXTag((void *)&tag);
  h->ffrGotoXTag((void *)&tag);

  bool truncated = false;
  do {
    if (h->ffrGetXTag((void *)&tag) != FSDB_RC_SUCCESS) break;
    unsigned long long t = tag2ull(&tag);
    if (t > to) break;
    ++out->total;

    if (t < from) {
      // 窗口之前：只记种子
      std::string v;
      if (vc_to_string(h, &v)) {
        out->has_seed = true;
        out->seed_time = t;
        out->seed_value = v;
      }
    } else {
      if (max_changes > 0 && (long long)out->times.size() >= max_changes) {
        truncated = true;
        break;
      }
      std::string v;
      if (vc_to_string(h, &v)) {
        out->times.push_back(t);
        out->values.push_back(v);
      }
    }
    if (t >= to) break;
  } while (h->ffrGotoNextVC() == FSDB_RC_SUCCESS);

  h->ffrFree();
  if (truncated) out->total = (unsigned long long)out->times.size();
  return true;
}

// 单个信号的「语义边沿」：只保留 0/1 且与上一次不同
static void make_edges(const VCWalker &w, std::vector<std::pair<unsigned long long, int> > *edges) {
  edges->clear();
  int prev = -1;
  for (size_t i = 0; i < w.values.size(); ++i) {
    const std::string &v = w.values[i];
    int cur = -1;
    if (v == "0") cur = 0;
    else if (v == "1") cur = 1;
    if (cur < 0 || cur == prev) continue;
    edges->push_back(std::make_pair(w.times[i], cur));
    prev = cur;
  }
}

// ------------------------------------------------------------------ usage

static void usage() {
  fprintf(stderr,
          "usage: fsdbq info   <fsdb>\n"
          "       fsdbq vars   <fsdb> [--pattern S] [--scope P] [--max-depth N] [--limit N]\n"
          "       fsdbq scopes <fsdb> [--scope P] [--max-depth N] [--limit N]\n"
          "       fsdbq wave   <fsdb> [--clock H|auto|none] [--pattern S]\n"
          "                           [--from T] [--to T] [--max-changes N] <sig>...\n");
}

// ------------------------------------------------------------------ main

int main(int argc, char **argv) {
  if (argc < 3) {
    usage();
    return 2;
  }
  const std::string mode = argv[1];
  const std::string path = argv[2];

  std::vector<std::string> sigs;
  unsigned long long from = 0;
  unsigned long long to = ~0ULL;
  long long max_changes = 2000000;
  std::string clock_opt = "auto";
  std::string pattern = "clk";   // 时钟候选名的子串（clock 模式）
  bool pattern_given = false;    // --pattern 是否显式给出（vars/scopes 过滤用）
  std::string scope_filter;
  long long limit = -1;
  long long max_depth = -1;

  for (int i = 3; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--from" && i + 1 < argc) {
      from = strtoull(argv[++i], NULL, 10);
    } else if (a == "--to" && i + 1 < argc) {
      to = strtoull(argv[++i], NULL, 10);
    } else if (a == "--max-changes" && i + 1 < argc) {
      max_changes = strtoll(argv[++i], NULL, 10);
    } else if (a == "--clock" && i + 1 < argc) {
      clock_opt = argv[++i];
    } else if (a == "--pattern" && i + 1 < argc) {
      pattern = argv[++i];
      pattern_given = true;
    } else if (a == "--scope" && i + 1 < argc) {
      scope_filter = argv[++i];
    } else if (a == "--limit" && i + 1 < argc) {
      limit = strtoll(argv[++i], NULL, 10);
    } else if (a == "--max-depth" && i + 1 < argc) {
      max_depth = strtoll(argv[++i], NULL, 10);
    } else if (!a.empty() && a[0] == '-') {
      fprintf(stderr, "ERR: unknown option %s\n", a.c_str());
      usage();
      return 2;
    } else {
      sigs.push_back(a);
    }
  }

  if (FALSE == ffrObject::ffrIsFSDB((char *)path.c_str())) {
    fprintf(stderr, "ERR: not an fsdb file: %s\n", path.c_str());
    return 3;
  }

  // ---- info：不需要打开对象
  if (mode == "info") {
    ffrFSDBInfo info;
    memset(&info, 0, sizeof(info));
    if (ffrObject::ffrGetFSDBInfo((char *)path.c_str(), info) != FSDB_RC_SUCCESS) {
      fprintf(stderr, "ERR: ffrGetFSDBInfo failed\n");
      return 4;
    }
    printf("I\tfile\t%s\n", path.c_str());
    printf("I\tscale_unit\t%s\n", info.scale_unit ? info.scale_unit : "");
    // FFR 的 version/date 字符串自带换行，去掉以免破坏行协议
    printf("I\tsim_version\t%s\n",
           chomp(info.simulator_version ? info.simulator_version : "").c_str());
    printf("I\tsim_date\t%s\n",
           chomp(info.simulation_date ? info.simulation_date : "").c_str());
    printf("I\tmin_time\t%llu\n",
           tag2ull((const fsdbTag64 *)&info.min_xtag));
    printf("I\tmax_time\t%llu\n",
           tag2ull((const fsdbTag64 *)&info.max_xtag));
    fflush(stdout);
    return 0;
  }

  ffrObject *obj = ffrObject::ffrOpen3((char *)path.c_str());
  if (!obj) {
    fprintf(stderr, "ERR: ffrOpen3 failed: %s\n", path.c_str());
    return 4;
  }

  Collector col;
  obj->ffrSetTreeCBFunc(tree_cb, (void *)&col);
  obj->ffrReadScopeVarTree();

  VarIndex idx;
  idx.build(col.vars);

  // ---- vars
  if (mode == "vars") {
    long long n = 0;
    for (size_t i = 0; i < col.vars.size(); ++i) {
      const VarRec &r = col.vars[i];
      if (max_depth >= 0 && VarIndex::depth_of(r) > max_depth) continue;
      if (!scope_filter.empty() && !has_prefix(r.hier, scope_filter)) continue;
      if (pattern_given && !has_substr_ci(r.hier, pattern)) continue;
      printf("V\t%s\t%d\t%d\t%d\t%s\t%d\n", r.hier.c_str(), (int)r.id, r.l, r.r,
             vtype_name(r.vtype), r.dir);
      if (limit > 0 && ++n >= limit) break;
    }
    printf("Z\tcount\t%llu\n", (unsigned long long)col.vars.size());
    obj->ffrClose();
    return 0;
  }

  // ---- scopes
  if (mode == "scopes") {
    long long n = 0;
    for (size_t i = 0; i < col.scopes.size(); ++i) {
      const ScopeRec &s = col.scopes[i];
      if (max_depth >= 0 && s.depth > max_depth) continue;
      if (!scope_filter.empty() && !has_prefix(s.hier, scope_filter)) continue;
      printf("S\t%s\t%d\n", s.hier.c_str(), s.depth);
      if (limit > 0 && ++n >= limit) break;
    }
    printf("Z\tcount\t%llu\n", (unsigned long long)col.scopes.size());
    obj->ffrClose();
    return 0;
  }

  if (mode != "wave") {
    fprintf(stderr, "ERR: unknown mode %s\n", mode.c_str());
    obj->ffrClose();
    return 2;
  }

  // ---- 波形：解析请求的信号（先解析，稍后与时钟候选一起加载）
  std::vector<fsdbVarIdcode> want_ids;
  std::vector<int> want_idx;
  for (size_t i = 0; i < sigs.size(); ++i) {
    bool exact = false;
    const VarRec *r = idx.resolve(col.vars, sigs[i], &exact);
    if (!r) {
      printf("N\t%llu\t%s\n", (unsigned long long)i, sigs[i].c_str());
      continue;
    }
    printf("B\t%llu\t%s\t%s\t%d\t%d\t%d\n", (unsigned long long)i,
           sigs[i].c_str(), r->hier.c_str(), (int)r->id, r->l, r->r);
    want_ids.push_back(r->id);
    want_idx.push_back((int)i);
  }

  // ---- 时钟候选集合
  // FFR 必须先 ffrAddToSignalList + ffrLoadSignals 才能建值变遍历句柄，
  // 所以候选与请求信号一起加载，全流程只加载一次。
  std::vector<int> cand_idx;
  if (clock_opt == "auto") {
    for (size_t i = 0; i < col.vars.size(); ++i) {
      const VarRec &r = col.vars[i];
      if (std::abs(r.l - r.r) + 1 != 1) continue;
      if (!has_substr_ci(r.name, pattern)) continue;
      cand_idx.push_back((int)i);
    }
  } else if (clock_opt != "none") {
    bool exact = false;
    const VarRec *cr = idx.resolve(col.vars, clock_opt, &exact);
    if (!cr || std::abs(cr->l - cr->r) + 1 != 1) {
      fprintf(stderr, "ERR: clock '%s' not found or not 1-bit\n",
              clock_opt.c_str());
      obj->ffrClose();
      return 5;
    }
    for (size_t i = 0; i < col.vars.size(); ++i)
      if (col.vars[i].hier == cr->hier) { cand_idx.push_back((int)i); break; }
  }

  // ---- 一次性加载信号表
  obj->ffrResetSignalList();
  for (size_t i = 0; i < want_ids.size(); ++i) obj->ffrAddToSignalList(want_ids[i]);
  for (size_t i = 0; i < cand_idx.size(); ++i)
    obj->ffrAddToSignalList(col.vars[cand_idx[i]].id);
  if (!want_ids.empty() || !cand_idx.empty()) obj->ffrLoadSignals();

  // ---- 时钟：与 ClockDetector::detect() 等价的候选打分 + 全时间段上升/下降沿
  std::string clock_hier;
  if (!cand_idx.empty()) {
    struct Cand {
      std::string hier;
      double period;
      double cv;
      int nedges;
      std::vector<unsigned long long> rising;
      std::vector<unsigned long long> falling;
    };
    std::vector<Cand> cands;
    for (size_t ci = 0; ci < cand_idx.size(); ++ci) {
      const VarRec &r = col.vars[cand_idx[ci]];
      VCWalker w;
      if (!walk_vc(obj, r.id, 0, ~0ULL, 0, &w)) continue;
      if (clock_opt == "auto" && w.values.size() < 4) continue;

      std::vector<std::pair<unsigned long long, int> > edges;
      make_edges(w, &edges);
      if (clock_opt == "auto" && edges.size() < 4) continue;

      Cand c;
      c.hier = r.hier;
      c.nedges = (int)edges.size();
      c.period = 0;
      c.cv = 0;
      for (size_t e = 1; e < edges.size(); ++e) {
        if (edges[e].second == 1 && edges[e - 1].second == 0)
          c.rising.push_back(edges[e].first);
        else if (edges[e].second == 0 && edges[e - 1].second == 1)
          c.falling.push_back(edges[e].first);
      }
      if (c.rising.size() >= 2) {
        double mean = 0;
        for (size_t k = 1; k < c.rising.size(); ++k)
          mean += (double)(c.rising[k] - c.rising[k - 1]);
        mean /= (double)(c.rising.size() - 1);
        if (mean > 0) {
          double var = 0;
          for (size_t k = 1; k < c.rising.size(); ++k) {
            double d = (double)(c.rising[k] - c.rising[k - 1]) - mean;
            var += d * d;
          }
          var /= (double)(c.rising.size() - 1);
          c.period = mean;
          c.cv = std::sqrt(var) / mean;
        }
      }
      if (clock_opt == "auto") {
        if (c.rising.size() < 2 || c.period <= 0) continue;
        double span = (double)(c.rising.back() - c.rising.front());
        if (span < c.period * 2) continue;
      }
      cands.push_back(c);
    }
    if (cands.empty()) {
      fprintf(stderr, "ERR: no clock detected (pattern='%s')\n", pattern.c_str());
      obj->ffrClose();
      return 6;
    }
    // 确定性 tie-break：cv 升序 -> nedges 降序 -> hier 升序
    size_t best = 0;
    for (size_t i = 1; i < cands.size(); ++i) {
      const Cand &a = cands[i];
      const Cand &b = cands[best];
      bool better = false;
      if (a.cv != b.cv) better = a.cv < b.cv;
      else if (a.nedges != b.nedges) better = a.nedges > b.nedges;
      else better = a.hier < b.hier;
      if (better) best = i;
    }
    const Cand &c = cands[best];
    clock_hier = c.hier;
    printf("C\t%s\t%.10g\t%.10g\t%d\t%llu\n", c.hier.c_str(), c.period, c.cv,
           c.nedges, (unsigned long long)c.rising.size());
    for (size_t i = 0; i < c.rising.size(); ++i) printf("R\t%llu\n", c.rising[i]);
    for (size_t i = 0; i < c.falling.size(); ++i) printf("F\t%llu\n", c.falling[i]);
  }


  for (size_t i = 0; i < want_ids.size(); ++i) {
    VCWalker w;
    walk_vc(obj, want_ids[i], from, to, max_changes, &w);
    int slot = want_idx[i];
    if (slot < 0) continue;  // 仅为时钟加载
    if (w.has_seed) printf("P\t%d\t%llu\t%s\n", slot, w.seed_time, w.seed_value.c_str());
    for (size_t k = 0; k < w.times.size(); ++k)
      printf("W\t%d\t%llu\t%s\n", slot, w.times[k], w.values[k].c_str());
    printf("E\t%d\t%llu\t%d\n", slot, w.total,
           (long long)w.times.size() < max_changes ? 0 : 1);
  }

  printf("Z\tclock\t%s\n", clock_hier.c_str());
  fflush(stdout);
  obj->ffrClose();
  return 0;
}
