module mini_top (
    input  [7:0] i_a,
    input  [7:0] i_b,
    output [7:0] o_y
);
    alu u_alu (.i_a(i_a), .i_b(i_b), .o_y(o_y));
endmodule
