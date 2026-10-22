; Leaf x64 probe: no pointers, imports or relocation-dependent operands.
PUBLIC LabCodeProbe, LabCodeProbeEnd, LabCodeSecondary, LabCodeSecondaryEnd
.code
LabCodeProbe PROC
    mov eax, ecx
    xor eax, 35h
    add eax, 17
    ret
LabCodeProbeEnd LABEL BYTE
LabCodeProbe ENDP
; Separate pages allow one unreadable range without losing the other.
DB 4096 DUP (090h)
LabCodeSecondary PROC
    mov eax, ecx
    add eax, 23
    ret
LabCodeSecondaryEnd LABEL BYTE
LabCodeSecondary ENDP
END
