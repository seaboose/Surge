"""Fixed-case contract for the bounded native boundary pack."""

GUARDS = (
    'if (reloc.Size >', 'if (reloc.Size) {',
    'if (reloc.Size - cursor <', 'if (block.SizeOfBlock <',
    'block.SizeOfBlock >', '(block.SizeOfBlock - sizeof(block)) %',
    'if (type == IMAGE_REL_BASED_ABSOLUTE)', 'if (type != IMAGE_REL_BASED_DIR64)',
    'if (target + 8 >', 'if (overlaps(rva, length, target, 8))',
    'if (!data.NumberOfFunctions || data.NumberOfFunctions > 4096 ||',
    'data.NumberOfNames > 4096)',
    'if (ordinal >= data.NumberOfFunctions)',
    'descriptor.range_count < 2 || descriptor.range_count > 16)',
)

COUNT_POSITIVE_CONTROLS = frozenset((
    'export_functions_4095', 'export_functions_4096',
    'export_names_4095', 'export_names_4096',
    'manifest_cardinality_2', 'manifest_cardinality_15', 'manifest_cardinality_16',
    'export_manifest_combined_max',
))


def case_ids():
    result = {'reloc_absent', 'reloc_zero_size_unmapped_rva', 'reloc_absolute_padding',
              'reloc_header_only', 'reloc_single_word', 'reloc_wide_target_addition',
              'reloc_unsupported_type', 'reloc_truncated_header', 'reloc_truncated_tail',
              'reloc_two_blocks', 'reloc_unmapped_span',
              'map_code_start', 'map_code_last_byte', 'map_code_end_empty',
              'map_code_end_one_byte', 'map_data_last_byte', 'map_data_cross_end',
              'map_image_end_empty', 'map_image_end_one_byte', 'map_image_past_end',
              'map_max_rva', 'map_max_size',
              'export_manifest_combined_max', 'export_final_ordinal_invalid',
              'manifest_unused_at_15'}
    for prefix, values in (
        ('reloc_target_', (0xff8,0xff9,0x1000,0x1008,0x1009,0x1018,0x1019,0x1020,0x1025,0x1026,0x3ff8,0x3ff9)),
        ('reloc_bad_block_size_', (0,7,9,13)),
        ('reloc_directory_size_', (1048576,1048577)),
        ('probe_length_', (0,1,63,64,65)),
        ('section_count_', (0,96,97)), ('executable_count_', (0,32,33)),
        ('image_size_', (0,0x3000,0x2fff,512*1024*1024,512*1024*1024+1)),
        ('declaration_count_', (1,17)), ('truncated_file_', (0,63,128,131,151,391,471)),
        ('export_functions_', (0,4095,4096,4097)),
        ('export_names_', (0,4095,4096,4097)),
        ('manifest_cardinality_', (0,1,2,15,16,17)),
        ('export_truncated_', ('functions','names','ordinals')),
        ('manifest_final_', ('duplicate','overlap','missing_end')),
    ):
        result.update(prefix+str(v) for v in values)
    return result


def parse_output(text):
    rows = []
    totals = []
    for line in text.splitlines():
        fields = line.split('\t')
        if fields[0] == 'CASE' and len(fields) == 5:
            _, identity, status, expected, actual = fields
            if status != 'PASS' or expected != actual:
                raise ValueError('Boundary expectation failed: '+identity)
            if identity in COUNT_POSITIVE_CONTROLS and actual != 'ACCEPT':
                raise ValueError('Count positive control was refused: '+identity)
            rows.append(dict(id=identity, status=status, expected=expected, actual=actual))
        elif fields[0] == 'TOTAL' and len(fields) == 3:
            totals.append((int(fields[1]),int(fields[2])))
        else:
            raise ValueError('Unexpected boundary output')
    if len(rows) != len(case_ids()) or {r['id'] for r in rows} != case_ids():
        raise ValueError('Missing or duplicate boundary cases')
    if totals != [(len(rows),0)] or not any(r['actual']=='ACCEPT' for r in rows):
        raise ValueError('Invalid boundary totals or missing positive control')
    return rows


def validate_evidence(data):
    rows = data['cases']
    if data['status'] != 'passed' or data['repeatability'] != 'passed':
        raise ValueError('Boundary pack incomplete')
    parse_output('\n'.join('\t'.join(('CASE',r['id'],r['status'],r['expected'],r['actual'])) for r in rows)
                 + f"\nTOTAL\t{len(rows)}\t0")
    if data['executions'] != 2*len(rows) or data['relocation_reader_executed'] is not True:
        raise ValueError('Missing boundary executions or reader coverage')
    guards = data['guards']
    if set(guards) != set(GUARDS):
        raise ValueError('Missing parser guard coverage')
    if any(not records or any(b[4] <= 0 or b[5] <= 0 for b in records) for records in guards.values()):
        raise ValueError('Parser guard outcome not covered')
    if {f['id'] for f in data['inputs']} != case_ids() or len(data['inputs']) != len(rows):
        raise ValueError('Missing boundary inputs')
    if any(not 0 <= f['bytes'] <= 65536 or len(f['sha256']) != 64 for f in data['inputs']):
        raise ValueError('Invalid boundary input evidence')
