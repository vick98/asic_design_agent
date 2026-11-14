class mini_tc_all;
  task body();
    mini_tc_basic tc1 = new("tc1");
    tc1.body();
  endtask
endclass
