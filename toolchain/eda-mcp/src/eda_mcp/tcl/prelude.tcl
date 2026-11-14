# prelude.tcl —— eda-mcp 设计模型 daemon 的 TCL 侧
#
# 由 daemon.py 在启动时 source 一次；之后每个请求脚本只调用
#     ::eda::dispatch <响应文件> <子命令> <参数>...
# 所有查询过程把结果按「记录类型 + TAB 分隔字段」写到响应文件。
#
# 记录类型：
#   H  depth full def file line          层次（模块/实例）
#   O  path type name full size dir nettype file line   对象属性
#   R  left right                        从源码声明行解析出的位宽范围
#   S  source_line                       声明所在源码行
#   P  parent name size direction line   端口
#   N  parent name size direction line   网络
#   A  parent name size direction line   参数
#   I  parent name size direction line   子实例
#   T  direction type full               驱动/负载
#   S  lhs_full lhs_text file line rhs_text   连续赋值语句
#   E  key value                         错误/提示
#   Z  key value                         汇总
#
# ⚠️ 设计模型用 npi_scan -iterator；FSDB 模型才是 -iter（见 NPI_TCL_REFERENCE.md）
# ⚠️ npiFullName 对 npiPort 为空，故端口的全名由父路径 + 名字拼出

namespace eval ::eda {
    variable version 1
    variable log ""
    variable fifo ""
}

# ---------------------------------------------------------------- 基础

proc ::eda::rec {fh args} {
    puts $fh [join $args "\t"]
}

proc ::eda::dispatch {out cmd args} {
    set fh [open $out w]
    set script [linsert $args 0 ::eda::q_$cmd $fh]
    set rc [catch { eval $script } err]
    if {$rc != 0} { catch { ::eda::rec $fh E error $err } }
    catch { ::eda::rec $fh Z rc $rc }
    catch { close $fh }
    return $rc
}

proc ::eda::attr {h prop} {
    if {[catch { npi_get_str -property $prop -object $h } v]} { return "" }
    if {$v eq "npiUndefined"} { return "" }
    return $v
}

proc ::eda::iattr {h prop} {
    if {[catch { npi_get -property $prop -object $h } v]} { return "" }
    return $v
}

proc ::eda::source_line {file line} {
    if {$file eq "" || $line <= 0} { return "" }
    if {[catch { set ch [open $file r] } e]} { return "" }
    set i 0
    set res ""
    while {[gets $ch buf] >= 0} {
        incr i
        if {$i == $line} { set res [string trim $buf]; break }
    }
    catch { close $ch }
    return $res
}

# 位宽：npiSize 对向量是「声明左界」、对标量是 1，单靠它无法区分，
# 故以源码声明行的 [msb:lsb] 为准（拿不到时才退回 npiSize）。
proc ::eda::range_of {h} {
    set type [::eda::attr $h npiType]
    set size [::eda::iattr $h npiSize]
    set file [::eda::attr $h npiFile]
    set line [::eda::iattr $h npiLineNo]
    set src [::eda::source_line $file $line]
    # 源码里写死的 [msb:lsb] 最可信
    if {[regexp {\[([0-9]+)\s*:\s*([0-9]+)\]} $src -> l r]} {
        return [list $l $r [expr {abs($l - $r) + 1}] $src]
    }
    # 参数/常量：npiSize 就是位宽本身
    if {$type eq "npiParameter" || $type eq "npiLocalParam" || $type eq "npiParameterBit"} {
        if {$size eq ""} { return [list "" "" 1 $src] }
        return [list "" "" $size $src]
    }
    # 信号：npiSize 是「声明左界」，标量固定给 1
    if {$size eq "" || $size <= 1} { return [list "" "" 1 $src] }
    return [list $size 0 [expr {$size + 1}] $src]
}

proc ::eda::emit_obj {fh parent h} {
    set name [::eda::attr $h npiName]
    set full [::eda::attr $h npiFullName]
    if {$full eq ""} {
        if {$parent eq ""} { set full $name } else { set full "$parent.$name" }
    }
    set file [::eda::attr $h npiFile]
    set line [::eda::iattr $h npiLineNo]
    lassign [::eda::range_of $h] l r w src
    ::eda::rec $fh O $full [::eda::attr $h npiType] $name \
        [::eda::attr $h npiDirection] [::eda::attr $h npiNetType] \
        $l $r $w $file $line $src
}

# ---------------------------------------------------------------- 查询

proc ::eda::q_ping {fh} {
    ::eda::rec $fh Z pong 1
}

proc ::eda::q_scopes {fh {root ""} {max_depth -1} {pattern ""}} {
    set n 0
    if {$root eq ""} {
        set itr [npi_iterate -type npiModule -refHandle ""]
        while {1} {
            set m [npi_scan -iterator $itr]
            if {$m eq ""} break
            ::eda::walk_scope $fh $m 0 $max_depth $pattern
            catch { npi_release_handle -object $m }
        }
    } else {
        set h [npi_handle_by_name -name $root -scope ""]
        if {$h eq ""} { ::eda::rec $fh E notfound $root; return }
        ::eda::walk_scope $fh $h 0 $max_depth $pattern
    }
    ::eda::rec $fh Z done 1
}

proc ::eda::walk_scope {fh h depth max_depth pattern} {
    set full [::eda::attr $h npiFullName]
    set name [::eda::attr $h npiName]
    if {$pattern eq "" || [string match $pattern $full] || [string match $pattern $name]} {
        ::eda::rec $fh H $depth $full [::eda::attr $h npiDefName] \
            [::eda::attr $h npiFile] [::eda::iattr $h npiLineNo]
    }
    if {$max_depth >= 0 && $depth >= $max_depth} { return }
    if {[catch { set itr [npi_iterate -type npiInstance -refHandle $h] } e]} { return }
    while {1} {
        if {[catch { set i [npi_scan -iterator $itr] } e]} { break }
        if {$i eq ""} break
        ::eda::walk_scope $fh $i [expr {$depth + 1}] $max_depth $pattern
        catch { npi_release_handle -object $i }
    }
}

proc ::eda::q_object {fh path} {
    set h [npi_handle_by_name -name $path -scope ""]
    if {$h eq ""} { ::eda::rec $fh E notfound $path; return }
    set parent ""
    set idx [string last "." $path]
    if {$idx > 0} { set parent [string range $path 0 [expr {$idx - 1}]] }
    ::eda::emit_obj $fh $parent $h
}

proc ::eda::q_module {fh path} {
    set h [npi_handle_by_name -name $path -scope ""]
    if {$h eq ""} { ::eda::rec $fh E notfound $path; return }
    set itr [npi_iterate -type npiInstance -refHandle $h]
    while {1} {
        set i [npi_scan -iterator $itr]
        if {$i eq ""} break
        ::eda::emit_obj $fh $path $i
        catch { npi_release_handle -object $i }
    }
    foreach t {npiPort npiNet npiParameter npiLocalParam npiReg npiBitVar npiLogicVar npiIntVar} {
        if {[catch { set it [npi_iterate -type $t -refHandle $h] } e]} { continue }
        while {1} {
            if {[catch { set o [npi_scan -iterator $it] } e]} { break }
            if {$o eq ""} break
            ::eda::emit_obj $fh $path $o
            catch { npi_release_handle -object $o }
        }
    }
    ::eda::rec $fh Z done 1
}

proc ::eda::q_find {fh pattern {limit 200}} {
    set seen [dict create]
    set n 0
    set itr [npi_iterate -type npiModule -refHandle ""]
    while {1} {
        set m [npi_scan -iterator $itr]
        if {$m eq ""} break
        ::eda::find_in $fh $m $pattern $limit seen n
        catch { npi_release_handle -object $m }
        if {$n >= $limit} break
    }
    ::eda::rec $fh Z count $n
}

proc ::eda::find_in {fh h pattern limit seenName nName} {
    upvar 1 $seenName seen $nName n
    foreach t {npiNet npiPort npiParameter npiReg npiBitVar npiLogicVar npiIntVar} {
        if {[catch { set it [npi_iterate -type $t -refHandle $h] } e]} { continue }
        while {1} {
            if {[catch { set o [npi_scan -iterator $it] } e]} { break }
            if {$o eq ""} break
            set name [::eda::attr $o npiName]
            set full [::eda::attr $o npiFullName]
            if {$full eq ""} { set p [::eda::attr $h npiFullName]; set full "$p.$name" }
            if {[string match $pattern $name] || [string match $pattern $full]} {
                if {![dict exists $seen $full]} {
                    dict set seen $full 1
                    ::eda::emit_obj $fh [::eda::attr $h npiFullName] $o
                    incr n
                }
            }
            catch { npi_release_handle -object $o }
            if {$n >= $limit} { return }
        }
    }
    if {[catch { set itr [npi_iterate -type npiInstance -refHandle $h] } e]} { return }
    while {1} {
        if {[catch { set i [npi_scan -iterator $itr] } e]} { break }
        if {$i eq ""} break
        ::eda::find_in $fh $i $pattern $limit seen n
        catch { npi_release_handle -object $i }
        if {$n >= $limit} { return }
    }
}

proc ::eda::q_trace {fh signal direction} {
    set res {}
    if {$direction eq "load"} {
        set rc [catch { ::npi_L1::npi_trace_load $signal res } e]
    } else {
        set rc [catch { ::npi_L1::npi_trace_driver $signal res } e]
    }
    if {$rc != 0} { ::eda::rec $fh E trace $e; return }
    set i 0
    foreach h $res {
        incr i
        set full [::eda::attr $h npiFullName]
        set name [::eda::attr $h npiName]
        set type [::eda::attr $h npiType]
        if {$full eq "" && $name eq ""} { set full "\[unnamed:$type\]" }
        if {$full eq ""} { set full $name }
        ::eda::rec $fh T $direction $type $full
    }
    ::eda::rec $fh Z count [llength $res]
}

proc ::eda::q_equiv {fh signal} {
    set res {}
    set rc [catch { ::npi_L1::npi_get_equivalent_signal $signal res } e]
    if {$rc != 0} { ::eda::rec $fh E equiv $e; return }
    foreach h $res {
        ::eda::rec $fh T equiv [::eda::attr $h npiType] [::eda::attr $h npiFullName]
    }
    ::eda::rec $fh Z count [llength $res]
}

# ------------------------------------------------------------ 语句图（连续赋值）
#
# S  lhs_full lhs_text file line rhs_text   连续赋值语句
#
# 供静态×动态联立（dbg trace/active）给驱动记录挂源码语境。**口径**：本查询
# 只覆盖连续赋值（assign）；always/initial 的过程赋值语句体在 Verdi NPI
# 无头模式（V-2023.12 实测）下不可达，过程驱动的寄存器拿不到语句语境，
# 由调用方如实标注，不得假装。作用域递归走 npiInternalScope（generate
# 作用域只有它能枚举，实测 npiInstance 在顶层返回 0）。

proc ::eda::emit_contassigns {fh mod depth max_depth nName} {
    upvar 1 $nName n
    if {[catch { set itr [npi_iterate -type npiContAssign -refHandle $mod] } e]} { return }
    set mod_full [::eda::attr $mod npiFullName]
    while {1} {
        if {[catch { set o [npi_scan -iterator $itr] } e]} { break }
        if {$o eq ""} break
        # 实测（V-2023.12）：npiLhs/npiRhs 属性返回空，但语句反编译可用，
        # 形如 "assign y_c = (a_r + b_r)"——lhs 名与 rhs 文本从反编译抽取。
        set dec ""
        catch { set dec [::npi_util_decompile_t::decompile $o] }
        set lhs_full ""
        set lhs_text ""
        set rhs_text ""
        if {[regexp {^assign\s+([^\s=]+)\s*=\s*(.+)$} $dec -> lhs_name rhs_text]} {
            set lhs_text $lhs_name
            if {$mod_full ne ""} { set lhs_full "$mod_full.$lhs_name" }
        }
        set file [::eda::attr $o npiFile]
        set line 0
        catch { set line [npi_get -property npiLineNo -object $o] }
        ::eda::rec $fh S $lhs_full $lhs_text $file $line $rhs_text
        incr n
    }
    if {$max_depth >= 0 && $depth >= $max_depth} { return }
    foreach kind {npiInternalScope npiInstance} {
        if {[catch { set itr [npi_iterate -type $kind -refHandle $mod] } e]} { continue }
        while {1} {
            if {[catch { set i [npi_scan -iterator $itr] } e]} { break }
            if {$i eq ""} break
            ::eda::emit_contassigns $fh $i [expr {$depth + 1}] $max_depth $nName
            catch { npi_release_handle -object $i }
        }
    }
}

proc ::eda::q_stmtmap {fh {root ""} {max_depth 8} {limit 5000}} {
    set n 0
    if {$root eq ""} {
        if {[catch { set itr [npi_iterate -type npiModule -refHandle ""] } e]} {
            ::eda::rec $fh E stmtmap $e
            return
        }
        while {1} {
            set m [npi_scan -iterator $itr]
            if {$m eq ""} break
            ::eda::emit_contassigns $fh $m 0 $max_depth n
            catch { npi_release_handle -object $m }
        }
    } else {
        set h [npi_handle_by_name -name $root -scope ""]
        if {$h eq ""} { ::eda::rec $fh E notfound $root; return }
        ::eda::emit_contassigns $fh $h 0 $max_depth n
    }
    ::eda::rec $fh Z count $n
}

# ---------------------------------------------------------------- 常驻循环

proc ::eda::serve_forever {} {
    set LOG $::eda::log
    while {1} {
        if {[catch { set chan [open $::eda::fifo r] } e]} {
            puts $LOG "fifo open failed: $e"; flush $LOG
            after 500
            continue
        }
        while {1} {
            if {[catch { gets $chan line } e]} { break }
            if {[eof $chan]} { break }
            set line [string trim $line]
            if {$line eq ""} { continue }
            if {$line eq "EXIT"} {
                catch { close $chan }
                catch { close $LOG }
                debExit
            }
            set rc [catch { uplevel #0 [list source $line] } res]
            puts $LOG "req=$line rc=$rc res=$res"
            flush $LOG
            if {[catch { set dh [open "$line.done" w]; puts $dh $rc; close $dh } e]} {
                puts $LOG "done marker failed: $e"; flush $LOG
            }
        }
        catch { close $chan }
    }
}
