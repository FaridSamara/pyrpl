/**
 * $Id: red_pitaya_pid_block.v 961 2014-01-21 11:40:39Z matej.oblak $
 *
 * @brief Red Pitaya PID controller.
 *
 * @Author Matej Oblak
 *
 * (c) Red Pitaya  http://www.redpitaya.com
 *
 * This part of code is written in Verilog hardware description language (HDL).
 * Please visit http://en.wikipedia.org/wiki/Verilog
 * for more details on the language used herein.
 */
/*
###############################################################################
#    pyrpl - DSP servo controller for quantum optics with the RedPitaya
#    Copyright (C) 2014-2016  Leonhard Neuhaus  (neuhaus@spectro.jussieu.fr)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
############################################################################### 
*/

module red_pitaya_trigger_block #(
   //parameters for input pre-filter
   parameter     FILTERSTAGES = 1,
   parameter     FILTERSHIFTBITS = 5,
   parameter     FILTERMINBW = 1
)
(
   // data
   input                 clk_i           ,  // clock
   input                 rstn_i          ,  // reset - active low
   input      [ 14-1: 0] dat_i           ,  // input data
   input      [ 14-1: 0] phase1_i         ,  // input phase to feed through
   output     [ 14-1: 0] dat_o           ,  // output data
   output     [ 14-1: 0] signal_o        ,  // output data
   output                trig_o          ,  // trigger signal
   input     [ 16-1: 0] trig_i          ,  // external trigger signal

   // communication with PS
   input      [ 16-1: 0] addr,
   input                 wen,
   input                 ren,
   output reg   		 ack,
   output reg [ 32-1: 0] rdata,
   input      [ 32-1: 0] wdata
);


//output states
localparam TTL = 4'd0;
localparam PHASE = 4'd1;
localparam MAXHOLD = 4'd2;
localparam MINHOLD = 4'd3;
localparam MEAN = 4'd4;


//settings
reg [ 32-1: 0] set_filter;   // input filter setting
reg [ 18-1: 0] trigger_source;
reg [  4-1: 0] output_select;
reg [ 14-1: 0] set_a_thresh;
reg [ 14-1: 0] set_a_hyst;
reg rearm;
reg auto_rearm;
reg [ 32-1: 0] auto_rearm_delay;
reg [ 14-1: 0] phase_offset;
reg phase_abs;
reg [ 5-1: 0] sum_divisor;
reg [32-1:0] trigger_delay;

//  System bus connection
always @(posedge clk_i) begin
   if (rstn_i == 1'b0) begin
      set_filter <= 32'd0;
      trigger_source <= 18'd0;
      output_select <= 4'b0000;
      set_a_thresh <= 14'd0;
      set_a_hyst <= 14'd20; // 2.5 mV by default
      rearm <= 1'b0;
      auto_rearm <= 1'b0;
      trigger_delay <= 32'd0;
      auto_rearm_delay <= 32'd0;
      phase_offset <= 14'd0;
      phase_abs <= 1'b0;
      sum_divisor <= 1'b0;
   end
   else begin
      if (addr==16'h100 && wen)
         rearm <= 1'b1;
      else
         rearm <= 1'b0;
      if (wen) begin
         if (addr==16'h104)   {phase_abs, auto_rearm} <= wdata[2-1:0];
         if (addr==16'h108)   trigger_source <= wdata[18-1:0];
         if (addr==16'h10C)   output_select <= wdata[4-1:0];
         if (addr==16'h110)   phase_offset <= wdata[14-1:0];
         if (addr==16'h118)   set_a_thresh <= wdata[14-1:0];
         if (addr==16'h11C)   set_a_hyst <= wdata[14-1:0];
         if (addr==16'h120)   set_filter  <= wdata;
         if (addr==16'h124)   auto_rearm_delay <= wdata;
         if (addr==16'h128)   sum_divisor <= wdata[5-1:0];
         if (addr==16'h12C)   trigger_delay <= wdata;
      end

	  casez (addr)
	     16'h100 : begin ack <= wen|ren; rdata <= {{32-1{1'b0}},armed}; end
	     16'h104 : begin ack <= wen|ren; rdata <= {{32-1{2'b0}},phase_abs,auto_rearm}; end
	     16'h108 : begin ack <= wen|ren; rdata <= {{32-18{1'b0}},trigger_source}; end
	     16'h10C : begin ack <= wen|ren; rdata <= {{32-4{1'b0}},output_select}; end
	     16'h110 : begin ack <= wen|ren; rdata <= {{32-14{1'b0}},phase_offset}; end

	     16'h118 : begin ack <= wen|ren; rdata <= set_a_thresh; end
	     16'h11C : begin ack <= wen|ren; rdata <= set_a_hyst; end
	     16'h120 : begin ack <= wen|ren; rdata <= set_filter; end
	     16'h124 : begin ack <= wen|ren; rdata <= auto_rearm_delay; end
	     16'h128 : begin ack <= wen|ren; rdata <= sum_divisor; end
	     16'h12C : begin ack <= wen|ren; rdata <= trigger_delay; end

	     16'h15C : begin ack <= wen|ren; rdata <= ctr_value[32-1:0]; end
	     16'h160 : begin ack <= wen|ren; rdata <= ctr_value[64-1:32]; end
	     16'h164 : begin ack <= wen|ren; rdata <= timestamp_trigger[32-1:0]; end
	     16'h168 : begin ack <= wen|ren; rdata <= timestamp_trigger[64-1:32]; end


	     16'h220 : begin ack <= wen|ren; rdata <= FILTERSTAGES; end
	     16'h224 : begin ack <= wen|ren; rdata <= FILTERSHIFTBITS; end
	     16'h228 : begin ack <= wen|ren; rdata <= FILTERMINBW; end

	     default: begin ack <= wen|ren;  rdata <=  32'h0; end
	  endcase	     
   end
end

//-----------------------------
// cascaded set of FILTERSTAGES low- or high-pass filters
wire signed [14-1:0] dat_i_filtered;
red_pitaya_filter_block #(
     .STAGES(FILTERSTAGES),
     .SHIFTBITS(FILTERSHIFTBITS),
     .SIGNALBITS(14),
     .MINBW(FILTERMINBW)
  )
  triggerfilter
  (
  .clk_i(clk_i),
  .rstn_i(rstn_i),
  .set_filter(set_filter), 
  .dat_i(dat_i),
  .dat_o(dat_i_filtered)
  );



//---------------------------------------------------------------------------------
//  Trigger created from input signal - nearly identical with scope
reg  [  2-1: 0] adc_scht_ap  ;
reg  [  2-1: 0] adc_scht_an  ;
reg  [ 14-1: 0] set_a_threshp ;
reg  [ 14-1: 0] set_a_threshm ;
reg adc_trig_ap;
reg adc_trig_an;

always @(posedge clk_i) begin
   set_a_threshp <= set_a_thresh + set_a_hyst ; // calculate positive
   set_a_threshm <= set_a_thresh - set_a_hyst ; // and negative threshold
   if (rstn_i == 1'b0) begin
      adc_scht_ap  <=  2'h0 ;
      adc_scht_an  <=  2'h0 ;
      adc_trig_ap  <=  1'b0 ;
      adc_trig_an  <=  1'b0 ;
   end else begin
      if ($signed(dat_i_filtered) >= $signed(set_a_thresh ))      adc_scht_ap[0] <= 1'b1 ;  // threshold reached
      else if ($signed(dat_i_filtered) <  $signed(set_a_threshm)) adc_scht_ap[0] <= 1'b0 ;  // wait until it goes under hysteresis
      if ($signed(dat_i_filtered) <= $signed(set_a_thresh ))      adc_scht_an[0] <= 1'b1 ;  // threshold reached
      else if ($signed(dat_i_filtered) >  $signed(set_a_threshp)) adc_scht_an[0] <= 1'b0 ;  // wait until it goes over hysteresis

      adc_scht_ap[1] <= adc_scht_ap[0] ;
      adc_scht_an[1] <= adc_scht_an[0] ;

      adc_trig_ap <= adc_scht_ap[0] && !adc_scht_ap[1] ; // make 1 cyc pulse
      adc_trig_an <= adc_scht_an[0] && !adc_scht_an[1] ;
   end
end

// trigger logic
reg trigger_signal;
reg armed;
reg   [ 64 - 1:0] ctr_value        ;
reg   [ 64 - 1:0] timestamp_trigger;
reg   [ 32 - 1:0] time_since_trigger;
reg   [ 14 - 1:0] phase_processed;
reg   [ 14 - 1:0] phase;
reg signed [ 14 - 1:0] max;
reg signed [ 14 - 1:0] min;
reg signed [ 14 - 1:0] maxout;
reg signed [ 14 - 1:0] minout;
reg   [ 14 - 1:0] output_data;
wire  [ 14 - 1:0] phase_i;
wire  [ 14 - 1:0] phase_sum;

reg signed [ 46 - 1:0] sum;
reg signed [ 14 - 1:0] sumout;


//multiplexer for input phase (still TODO)
assign phase_i = phase1_i;
//account for offset
assign phase_sum = phase_i + phase_offset;

reg do_auto_rearm;
reg post_trigger_delay_running;

reg trigger_delay_running;
reg [32-1:0] trigger_delay_count;

reg [18-1:0] last_trig;
reg [18-1:0] last_last_trig;
reg trig_high;
reg buffered_trigger_signal;

wire [46-1:0] shifted_sum;

always @(posedge clk_i)
if (rstn_i == 1'b0) begin
   trigger_signal <= 1'b0;
   armed <= 1'b0;
   do_auto_rearm <= 1'b0;
   ctr_value <= 64'h0;
   timestamp_trigger <= 64'h0;
   time_since_trigger <= 32'h0;
   phase <= 14'd0;
   output_data <= 14'd0;
   phase_processed <= 14'd0;
   post_trigger_delay_running <= 1'b0;
   trigger_delay_running <= 1'b0;
   trigger_delay_count <= 32'd0;
   min <= 14'd0;
   max <= 14'd0;
   minout <= 14'd0;
   maxout <= 14'd0;
   last_trig <= 18'd0;
   last_last_trig <= 18'd0;
   trig_high <= 1'b0;
   buffered_trigger_signal <= 1'b0;
   sum <= 46'd0;
   sumout <= 14'd0;
end else begin
   // handle external trigger with bits 0 through 15 of trigger_source
   // bit 16 of trigger_source defines positive slope trigger, bit 17 negative_slope trigger
   last_trig <= {adc_trig_an, adc_trig_ap, trig_i};
   last_last_trig <= last_trig;
   trig_high <= (|(last_trig & (~last_last_trig) & trigger_source));

   // time counter
   ctr_value <= ctr_value + 1'b1;

   // disarm after trigger event, rearm when requested explicitly or required for auto_rearm;
   // make sure armed stays low from initial trigger event until the end of post_trigger_delay
   armed <= (((armed && (!trigger_signal) && (!buffered_trigger_signal)) || rearm || do_auto_rearm) && !post_trigger_delay_running && !trigger_delay_running);

   // manage trigger delay counter
   if (trigger_delay_running)
      trigger_delay_count <= trigger_delay_count - 32'd1;
   else
      trigger_delay_count <= trigger_delay;

   if (trig_high && armed) begin
      // start trigger delay
      trigger_delay_running <= 1'b1;
      buffered_trigger_signal <= 1'b0;
   end else if (trigger_delay_running && (trigger_delay_count == 32'd0)) begin
      // end trigger delay: send out a trigger pulse
      trigger_delay_running <= 1'b0;
      buffered_trigger_signal <= 1'b1;
   end else begin
      // otherwise, make sure trigger is always zero
      buffered_trigger_signal <= 1'b0;
   end

   // actual trigger is delayed version of buffered trigger
   trigger_signal <= buffered_trigger_signal;

   // at the moment of the trigger event
   if (trigger_signal==1'b1) begin
       timestamp_trigger <= ctr_value;  // take a timestamp
       post_trigger_delay_running = 1'b1;  // activate post_trigger logic
       time_since_trigger <= 32'd1;  // start counting time after trigger
       phase <= phase_processed;  // store the phase at trigger time
       min <= dat_i_filtered;
       max <= dat_i_filtered;
       sum <= {{32{dat_i_filtered[14-1]}}, dat_i_filtered};
   end else begin
       time_since_trigger <= time_since_trigger + 1'b1;  // increment time counter since trigger event
       if (time_since_trigger > auto_rearm_delay) begin
           post_trigger_delay_running <= 1'b0;
           // auto_rearm exactly when the post_trigger_delay is just over
           if (post_trigger_delay_running) begin
               do_auto_rearm <= auto_rearm;
               minout <= min;
               maxout <= max;
               sumout <= shifted_sum[14-1:0];
           end
       end else begin
           if (post_trigger_delay_running) begin
               max <= (dat_i_filtered > max) ? dat_i_filtered : max;
               min <= (dat_i_filtered < min) ? dat_i_filtered : min;
               sum <= $signed(sum) + $signed({{32{dat_i_filtered[14-1]}}, dat_i_filtered});
           end
       end
   end

   // compute phase output
   if ((phase_abs == 1'b1) && (phase_sum[14-1] == 1'b1))
       phase_processed <= (~phase_sum)+14'd1;
   else
       phase_processed <= phase_sum;

   // output_signal multiplexer
   if (output_select==TTL)
       output_data <= {1'b0,{13{trigger_signal}}};
   else if (output_select==PHASE)
       output_data <= phase;
   else if (output_select==MAXHOLD)
       output_data <= maxout;
   else if (output_select==MINHOLD)
       output_data <= minout;
   else if (output_select==MEAN)
       output_data <= sumout;

end

assign shifted_sum = sum >>> sum_divisor;

assign dat_o = output_data;
assign signal_o = output_data;
assign trig_o = trigger_signal;

endmodule
