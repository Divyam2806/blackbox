; 8085 Assembly Program: Unpack Packed BCD Number into Two Separate Memory Locations
LDA 2200H	;get the packed BCD number
ANI 0F0H	;mask the lower nibble
RRC		
RRC
RRC
RRC		;adjust higher BCD digit as a lower digit
STA 2301H	;store the partial result
LDA 2200H	;get the original BCD number
ANI 00FH	;mask the higher nibble
STA 2201H	;store the result
HLT
