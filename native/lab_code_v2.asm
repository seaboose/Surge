; Reviewed alternate build with an intentionally different immediate operand.
PUBLIC LabCodeProbe, LabCodeProbeEnd, LabCodeSecondary, LabCodeSecondaryEnd
PUBLIC LabCodeTertiary, LabCodeTertiaryEnd
.code
LabCodeProbe PROC
    mov eax, ecx
    xor eax, 46h
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
DB 4096 DUP (090h)
LabCodeTertiary PROC
    mov eax, ecx
    imul eax, eax, 3
    add eax, 7
    ret
LabCodeTertiaryEnd LABEL BYTE
LabCodeTertiary ENDP
END
