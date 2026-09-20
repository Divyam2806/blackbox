; Intel 8085 Microprocessor Assembly Sample Firmware
; Temperature Sensor & Cooler Control Unit
;
; Hardware Interface:
;   Port 01H: ADC Sensor Input (Temperature reading)
;   Port 02H: Cooler Actuator Output (00H=OFF, 01H=ON)
;   Port 03H: Overheat Alarm LED Output (00H=OFF, 01H=ON)

START:  IN 01H         ; Read ADC temperature from Port 01H
        CPI 30H        ; Compare temperature with 30 (0x1E)
        JC FAN_OFF     ; If Temperature < 30, turn Cooler OFF
        
FAN_ON: MVI A, 01H     ; Accumulator = 01H (ON)
        OUT 02H        ; Drive Cooler ON at Port 02H
        JMP CHECK_ALARM

FAN_OFF:MVI A, 00H     ; Accumulator = 00H (OFF)
        OUT 02H        ; Drive Cooler OFF at Port 02H

CHECK_ALARM:
        IN 01H         ; Re-read temperature
        CPI 50H        ; Check critical overheat threshold (50 deg C)
        JC NO_ALARM
        MVI A, 01H     ; Alarm ON
        OUT 03H        ; Drive Alarm LED at Port 03H
        JMP LOOP

NO_ALARM:
        MVI A, 00H     ; Alarm OFF
        OUT 03H

LOOP:   HLT            ; Halt Microprocessor
