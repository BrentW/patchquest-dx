"""Linear 65816 disassembly for evidence gathering, not automatic code discovery.

M/X state follows REP/SEP only. Calls, PLP, RTI, XCE and alternate paths need manual
state validation. Branch targets are printed; data can still decode as instructions.
"""
import argparse
from pathlib import Path

# Each cell is mnemonic:address-mode. m/x immediates use selected CPU flag widths.
ROWS = [
"BRK:b ORA:diX COP:b ORA:sr TSB:d ORA:d ASL:d ORA:dl PHP:i ORA:m ASL:a PHD:i TSB:w ORA:w ASL:w ORA:l",
"BPL:r ORA:diY ORA:di ORA:sriY TRB:d ORA:dX ASL:dX ORA:dlY CLC:i ORA:wY INC:a TCS:i TRB:w ORA:wX ASL:wX ORA:lX",
"JSR:w AND:diX JSL:l AND:sr BIT:d AND:d ROL:d AND:dl PLP:i AND:m ROL:a PLD:i BIT:w AND:w ROL:w AND:l",
"BMI:r AND:diY AND:di AND:sriY BIT:dX AND:dX ROL:dX AND:dlY SEC:i AND:wY DEC:a TSC:i BIT:wX AND:wX ROL:wX AND:lX",
"RTI:i EOR:diX WDM:b EOR:sr MVP:mv EOR:d LSR:d EOR:dl PHA:i EOR:m LSR:a PHK:i JMP:w EOR:w LSR:w EOR:l",
"BVC:r EOR:diY EOR:di EOR:sriY MVN:mv EOR:dX LSR:dX EOR:dlY CLI:i EOR:wY PHY:i TCD:i JML:l EOR:wX LSR:wX EOR:lX",
"RTS:i ADC:diX PER:R ADC:sr STZ:d ADC:d ROR:d ADC:dl PLA:i ADC:m ROR:a RTL:i JMP:wi ADC:w ROR:w ADC:l",
"BVS:r ADC:diY ADC:di ADC:sriY STZ:dX ADC:dX ROR:dX ADC:dlY SEI:i ADC:wY PLY:i TDC:i JMP:wiX ADC:wX ROR:wX ADC:lX",
"BRA:r STA:diX BRL:R STA:sr STY:d STA:d STX:d STA:dl DEY:i BIT:m TXA:i PHB:i STY:w STA:w STX:w STA:l",
"BCC:r STA:diY STA:di STA:sriY STY:dX STA:dX STX:dY STA:dlY TYA:i STA:wY TXS:i TXY:i STZ:w STA:wX STZ:wX STA:lX",
"LDY:x LDA:diX LDX:x LDA:sr LDY:d LDA:d LDX:d LDA:dl TAY:i LDA:m TAX:i PLB:i LDY:w LDA:w LDX:w LDA:l",
"BCS:r LDA:diY LDA:di LDA:sriY LDY:dX LDA:dX LDX:dY LDA:dlY CLV:i LDA:wY TSX:i TYX:i LDY:wX LDA:wX LDX:wY LDA:lX",
"CPY:x CMP:diX REP:b CMP:sr CPY:d CMP:d DEC:d CMP:dl INY:i CMP:m DEX:i WAI:i CPY:w CMP:w DEC:w CMP:l",
"BNE:r CMP:diY CMP:di CMP:sriY PEI:di CMP:dX DEC:dX CMP:dlY CLD:i CMP:wY PHX:i STP:i JML:wl CMP:wX DEC:wX CMP:lX",
"CPX:x SBC:diX SEP:b SBC:sr CPX:d SBC:d INC:d SBC:dl INX:i SBC:m NOP:i XBA:i CPX:w SBC:w INC:w SBC:l",
"BEQ:r SBC:diY SBC:di SBC:sriY PEA:w SBC:dX INC:dX SBC:dlY SED:i SBC:wY PLX:i XCE:i JSR:wiX SBC:wX INC:wX SBC:lX",
]
OPS = [cell.split(":") for row in ROWS for cell in row.split()]


def lorom_cpu(offset):
    if not 0 <= offset < 0x400000:
        raise ValueError("Only ordinary <=4 MiB LoROM supported")
    return ((offset // 0x8000) << 16) | 0x8000 | (offset % 0x8000)


def disassemble(data, start, end, m8=True, x8=False):
    pos = start
    while pos < end:
        op = data[pos]; name, mode = OPS[op]
        if mode in ("i", "a"): n = 0
        elif mode == "m": n = 1 if m8 else 2
        elif mode == "x": n = 1 if x8 else 2
        elif mode.startswith("l"): n = 3
        elif mode.startswith("w") or mode in ("R", "mv"): n = 2
        else: n = 1
        raw = data[pos:pos+1+n]
        if len(raw) != 1+n:
            raise ValueError("Truncated instruction")
        v = int.from_bytes(raw[1:], "little")
        operand = f"${v:0{n*2}X}" if n else ("A" if mode == "a" else "")
        if mode in ("m", "x", "b"): operand = "#" + operand
        if mode in ("r", "R"):
            displacement = int.from_bytes(raw[1:], "little", signed=True)
            target = (lorom_cpu(pos) & 0xff0000) | ((lorom_cpu(pos)+1+n+displacement)&0xffff)
            operand = f"${target:06X}"
        if mode in ("di", "diX", "diY", "sriY", "wi", "wiX"): operand = "(" + operand + (",X" if mode.endswith("iX") else "") + ")" + (",Y" if mode.endswith("Y") else "")
        elif mode in ("dl", "dlY", "wl"): operand = "[" + operand + "]" + (",Y" if mode.endswith("Y") else "")
        elif mode.endswith(("X", "Y")): operand += "," + mode[-1]
        if mode in ("sr", "sriY"): operand += " {stack-relative}"
        warning = " ; state/control-flow boundary: validate manually" if name in ("PLP","RTI","XCE","JSL","JSR") else ""
        yield f"{pos:06X}  {lorom_cpu(pos):06X}  {raw.hex(' '):11s} {name:3s} {operand}{warning}"
        if op in (0xc2, 0xe2):
            if v & 0x20: m8 = op == 0xe2
            if v & 0x10: x8 = op == 0xe2
        pos += 1+n
