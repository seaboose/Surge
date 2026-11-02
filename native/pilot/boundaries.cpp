#define NOMINMAX
#include "seed.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#if !__has_feature(address_sanitizer)
#error Boundary qualification requires AddressSanitizer
#endif

namespace {
struct Case {
  std::string id;
  std::vector<unsigned char> bytes;
  std::string expected = "ACCEPT";
  std::vector<LabImage::ResolvedRange> expected_ranges;
  bool mapping = false;
  DWORD query = 0;
  std::size_t length = 0, mapped = 0;
  unsigned first_length = 9;
  DWORD first_rva = 0x1000, second_rva = 0x1020;
  std::vector<LabImage::Span> spans{{0x1000, 512}};
};
constexpr std::size_t relocation_at = 1024 + 0xc00;
template<class T> T get(const std::vector<unsigned char>& bytes, std::size_t at) {
  T result{};
  if (at > bytes.size() || sizeof(T) > bytes.size() - at)
    throw std::logic_error("Invalid fixture read");
  std::memcpy(&result, bytes.data()+at, sizeof(T));
  return result;
}
void directory(Case& c, DWORD rva, DWORD size) {
  auto opt=get<IMAGE_OPTIONAL_HEADER64>(c.bytes, optional_at);
  opt.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC]={rva,size};
  put(c.bytes, optional_at, opt);
}
void block(Case& c, DWORD page, WORD entry, DWORD size=12) {
  directory(c,0x2c00,size);
  put(c.bytes,relocation_at,IMAGE_BASE_RELOCATION{page,size});
  put(c.bytes,relocation_at+8,entry);
  put(c.bytes,relocation_at+10,WORD(0));
}
// Independent small-domain oracle: enumerate the eight affected bytes rather
// than use the parser's overlap predicate or its parsed interval information.
bool touches_declared(std::uint64_t target) {
  for(unsigned i=0;i<8;++i) {
    auto byte=target+i;
    if ((byte>=0x1000 && byte<0x1009) || (byte>=0x1020 && byte<0x1026)) return true;
  }
  return false;
}
void many_sections(Case& c, unsigned total, unsigned executable) {
  auto old=c.bytes;
  c.bytes.assign(13312 + 32 * executable, 0);
  std::copy(old.begin(),old.begin()+512,c.bytes.begin());
  std::copy(old.begin()+512,old.end(),c.bytes.begin()+8192);
  auto file=get<IMAGE_FILE_HEADER>(c.bytes,132);file.NumberOfSections=static_cast<WORD>(total);put(c.bytes,132,file);
  auto opt=get<IMAGE_OPTIONAL_HEADER64>(c.bytes,optional_at);opt.SizeOfHeaders=8192;opt.SizeOfImage=0x10000;opt.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT].VirtualAddress=0x3000;put(c.bytes,optional_at,opt);
  auto code=get<IMAGE_SECTION_HEADER>(old,section_at);code.PointerToRawData=8192;code.VirtualAddress=0x2000;
  if (!executable) code.Characteristics=IMAGE_SCN_MEM_READ;
  put(c.bytes,section_at,code);
  auto data=get<IMAGE_SECTION_HEADER>(old,section_at+sizeof(code));data.PointerToRawData=8704;data.VirtualAddress=0x3000;put(c.bytes,section_at+sizeof(code),data);
  auto exports=get<IMAGE_EXPORT_DIRECTORY>(c.bytes,8704);
  exports.AddressOfFunctions+=0x1000;exports.AddressOfNames+=0x1000;exports.AddressOfNameOrdinals+=0x1000;put(c.bytes,8704,exports);
  for(unsigned i=0;i<5;++i) {
    auto address=get<DWORD>(c.bytes,8704+0x40+i*4);put(c.bytes,8704+0x40+i*4,DWORD(address+0x1000));
    auto name=get<DWORD>(c.bytes,8704+0x60+i*4);put(c.bytes,8704+0x60+i*4,DWORD(name+0x1000));
  }
  c.first_rva=0x2000;c.second_rva=0x2020;
  c.spans.clear();if(executable)c.spans.push_back({0x2000,512});
  for(unsigned i=2;i<total;++i) {
    IMAGE_SECTION_HEADER section{};
    if(i<executable+1) {
      section.VirtualAddress=0x5000+(i-2)*0x100;
      section.PointerToRawData=13312+(i-2)*32;
      section.SizeOfRawData=section.Misc.VirtualSize=32;
      section.Characteristics=IMAGE_SCN_MEM_READ|IMAGE_SCN_MEM_EXECUTE;
      c.spans.push_back({section.VirtualAddress,32});
    }
    put(c.bytes,section_at+i*sizeof(section),section);
  }
}
// Actual maximum-size tables and unique short filler names fit below 64 KiB.
constexpr std::size_t count_functions = 1024 + 0x900;
constexpr std::size_t count_names = 1024 + 0x4900;
constexpr std::size_t count_ordinals = 1024 + 0x8900;
constexpr std::size_t count_descriptor = 1024 + 0x40;
void cardinality_fixture(Case& c, unsigned declared, DWORD functions, DWORD names) {
  const unsigned populated = std::max(2u, std::min(16u, declared));
  const unsigned symbols = 2 * populated + 1;
  const DWORD allocated_functions = std::max(DWORD(symbols), std::min(DWORD(4096), functions));
  const DWORD allocated_names = std::max(DWORD(symbols), std::min(DWORD(4096), names));
  c.bytes.resize(64512, 0);
  std::fill(c.bytes.begin()+1024,c.bytes.end(),0);
  auto optional=get<IMAGE_OPTIONAL_HEADER64>(c.bytes,optional_at);
  optional.SizeOfImage=0x12000;optional.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT]={0x2000,40};put(c.bytes,optional_at,optional);
  auto data=get<IMAGE_SECTION_HEADER>(c.bytes,section_at+sizeof(IMAGE_SECTION_HEADER));
  data.Misc.VirtualSize=data.SizeOfRawData=0xf800;put(c.bytes,section_at+sizeof(IMAGE_SECTION_HEADER),data);
  IMAGE_EXPORT_DIRECTORY exports{};exports.NumberOfFunctions=functions;exports.NumberOfNames=names;
  exports.AddressOfFunctions=0x2900;exports.AddressOfNames=0x6900;exports.AddressOfNameOrdinals=0xa900;put(c.bytes,1024,exports);
  LabManifestDeclaration manifest{};manifest.magic=lab_manifest_magic;manifest.version=1;manifest.machine=IMAGE_FILE_MACHINE_AMD64;manifest.range_count=declared;
  std::vector<std::string> required;std::vector<DWORD> addresses;
  for(unsigned i=0;i<populated;++i) {
    const std::string begin="Range"+std::string(1,char('A'+i)), end=begin+"End";
    std::memcpy(manifest.ranges[i].begin,begin.c_str(),begin.size()+1);
    std::memcpy(manifest.ranges[i].end,end.c_str(),end.size()+1);
    const DWORD rva=0x1000+16*i;const unsigned length=1+i%7;const unsigned char byte=static_cast<unsigned char>(0x40+i);
    std::fill(c.bytes.begin()+512+16*i,c.bytes.begin()+512+16*i+length,byte);
    c.expected_ranges.push_back({begin,rva,std::vector<unsigned char>(length,byte)});
    required.push_back(begin);required.push_back(end);addresses.push_back(rva);addresses.push_back(rva+length);
  }
  required.push_back("LabIntegrityManifest");addresses.push_back(0x2040);put(c.bytes,count_descriptor,manifest);
  std::size_t string_at=1024+0xa900;
  const std::string alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_@";
  for(DWORD i=0;i<allocated_names;++i) {
    const bool wanted=i>=allocated_names-symbols;
    const auto index=wanted?i-(allocated_names-symbols):0;
    const std::string name=wanted?required[index]:"X"+std::string(1,alphabet[(i/64)%64])+std::string(1,alphabet[i%64]);
    if(string_at+name.size()+1>c.bytes.size())throw std::logic_error("Count fixture string budget");
    std::memcpy(c.bytes.data()+string_at,name.c_str(),name.size()+1);
    put(c.bytes,count_names+4*i,DWORD(0x2000+string_at-1024));
    put(c.bytes,count_ordinals+2*i,WORD(wanted?allocated_functions-symbols+index:0));
    string_at+=name.size()+1;
  }
  for(unsigned i=0;i<symbols;++i)put(c.bytes,count_functions+4*(allocated_functions-symbols+i),addresses[i]);
}
std::vector<Case> cases() {
  auto base=fixture();
  auto opt=get<IMAGE_OPTIONAL_HEADER64>(base,optional_at);opt.ImageBase=0x140000000ULL;put(base,optional_at,opt);
  std::vector<Case> result;
  auto add=[&](const std::string& id)->Case& {result.push_back(Case{id,base});return result.back();};
  add("reloc_absent");
  directory(add("reloc_zero_size_unmapped_rva"),0xffffffff,0);
  block(add("reloc_absolute_padding"),0xffffffff,WORD(0x0fff));
  block(add("reloc_header_only"),0x1000,0,8);
  block(add("reloc_single_word"),0x1000,0,10);
  for(DWORD target:{0x0ff8u,0x0ff9u,0x1000u,0x1008u,0x1009u,0x1018u,0x1019u,0x1020u,0x1025u,0x1026u,0x3ff8u,0x3ff9u}) {
    auto& c=add("reloc_target_"+std::to_string(target));
    block(c,target&~DWORD(0xfff),WORD((IMAGE_REL_BASED_DIR64<<12)|(target&0xfff)));
    if(std::uint64_t(target)+8>0x4000) c.expected="Relocation target outside image";
    else if(touches_declared(target)) c.expected="Probe intersects relocation fixup; comparison refused";
  }
  {
    auto& c=add("reloc_wide_target_addition");block(c,0xffffffff,WORD((IMAGE_REL_BASED_DIR64<<12)|0xfff));c.expected="Relocation target outside image";
  }
  {
    auto& c=add("reloc_unsupported_type");block(c,0x1000,WORD(IMAGE_REL_BASED_HIGHLOW<<12));c.expected="Unsupported relocation type";
  }
  for(DWORD size:{0u,7u,9u,13u}) {
    auto& c=add("reloc_bad_block_size_"+std::to_string(size));block(c,0x1000,0);put(c.bytes,relocation_at,IMAGE_BASE_RELOCATION{0x1000,size});c.expected="Invalid relocation block";
  }
  {
    auto& c=add("reloc_truncated_header");directory(c,0x2c00,7);c.expected="Truncated relocation block";
  }
  {
    auto& c=add("reloc_truncated_tail");block(c,0x1000,0);directory(c,0x2c00,13);c.expected="Truncated relocation block";
  }
  {
    auto& c=add("reloc_two_blocks");block(c,0x1000,WORD((IMAGE_REL_BASED_DIR64<<12)|0x80));directory(c,0x2c00,24);
    put(c.bytes,relocation_at+12,IMAGE_BASE_RELOCATION{0x2000,12});put(c.bytes,relocation_at+20,WORD(IMAGE_REL_BASED_DIR64<<12));
  }
  for(DWORD size:{1048576u,1048577u}) {
    auto& c=add("reloc_directory_size_"+std::to_string(size));directory(c,0x2c00,size);
    c.expected=size==1048576 ? "RVA outside image" : "Relocation directory exceeds lab limit";
  }
  {
    auto& c=add("reloc_unmapped_span");directory(c,0x2ffc,12);c.expected="RVA has no unique file-backed section";
  }
  for(unsigned length:{0u,1u,63u,64u,65u}) {
    auto& c=add("probe_length_"+std::to_string(length));c.first_length=length;c.second_rva=0x1080;
    put(c.bytes,1024+0x44,DWORD(0x1000+length));put(c.bytes,1024+0x48,DWORD(0x1080));put(c.bytes,1024+0x4c,DWORD(0x1086));
    if(!length||length>64)c.expected="Unsupported probe length";
  }
  for(unsigned count:{0u,96u,97u}) {
    auto& c=add("section_count_"+std::to_string(count));many_sections(c,96,1);
    auto file=get<IMAGE_FILE_HEADER>(c.bytes,132);file.NumberOfSections=static_cast<WORD>(count);put(c.bytes,132,file);
    if(count!=96)c.expected="Unsupported lab image architecture or headers";
  }
  for(unsigned count:{0u,32u,33u}) {
    auto& c=add("executable_count_"+std::to_string(count));many_sections(c,count+2,count);
    if(count!=32)c.expected="Unsupported executable section count";
  }
  for(DWORD size:{0u,0x3000u,0x2fffu,512u*1024*1024,512u*1024*1024+1}) {
    auto& c=add("image_size_"+std::to_string(size));auto header=get<IMAGE_OPTIONAL_HEADER64>(c.bytes,optional_at);header.SizeOfImage=size;put(c.bytes,optional_at,header);
    if(!size||size>512u*1024*1024)c.expected="Unsupported optional header";
    else if(size==0x2fff)c.expected="PE section exceeds file or image";
  }
  for(unsigned count:{1u,17u}) {
    auto& c=add("declaration_count_"+std::to_string(count));auto declaration=get<LabManifestDeclaration>(c.bytes,declaration_at);declaration.range_count=count;put(c.bytes,declaration_at,declaration);c.expected="Unsupported integrity manifest declaration";
  }
  for(std::size_t cut:{std::size_t(0),std::size_t(63),std::size_t(128),std::size_t(131),std::size_t(151),optional_at+sizeof(IMAGE_OPTIONAL_HEADER64)-1,section_at+2*sizeof(IMAGE_SECTION_HEADER)-1}) {
    auto& c=add("truncated_file_"+std::to_string(cut));c.bytes.resize(cut);
    c.expected=cut>=optional_at+sizeof(IMAGE_OPTIONAL_HEADER64) ? "Unsupported optional header" : "PE structure exceeds captured file";
  }
  auto map=[&](const char* id,DWORD rva,std::size_t length,std::size_t at,const char* refusal="ACCEPT") {
    auto& c=add(id);c.mapping=true;c.query=rva;c.length=length;c.mapped=at;c.expected=refusal;
  };
  map("map_code_start",0x1000,1,512);
  map("map_code_last_byte",0x11ff,1,1023);
  map("map_code_end_empty",0x1200,0,1024);
  map("map_code_end_one_byte",0x1200,1,0,"RVA has no unique file-backed section");
  map("map_data_last_byte",0x2fff,1,5119);
  map("map_data_cross_end",0x2fff,2,0,"RVA has no unique file-backed section");
  map("map_image_end_empty",0x4000,0,0,"RVA has no unique file-backed section");
  map("map_image_end_one_byte",0x4000,1,0,"RVA outside image");
  map("map_image_past_end",0x4001,0,0,"RVA outside image");
  map("map_max_rva",0xffffffff,1,0,"RVA outside image");
  map("map_max_size",0x1000,std::numeric_limits<std::size_t>::max(),0,"RVA outside image");
  for(DWORD count:{0u,4095u,4096u,4097u}) {
    auto& c=add("export_functions_"+std::to_string(count));cardinality_fixture(c,2,count,5);
    if(!count||count>4096)c.expected="Unsupported export count";
  }
  for(DWORD count:{0u,4095u,4096u,4097u}) {
    auto& c=add("export_names_"+std::to_string(count));cardinality_fixture(c,2,5,count);
    if(!count)c.expected="Required lab probe export is absent";
    else if(count>4096)c.expected="Unsupported export count";
  }
  for(unsigned count:{0u,1u,2u,15u,16u,17u}) {
    auto& c=add("manifest_cardinality_"+std::to_string(count));cardinality_fixture(c,count,33,33);
    if(count<2||count>16)c.expected="Unsupported integrity manifest declaration";
  }
  cardinality_fixture(add("export_manifest_combined_max"),16,4096,4096);
  {
    auto& c=add("export_final_ordinal_invalid");cardinality_fixture(c,16,4096,4096);
    put(c.bytes,count_ordinals+2*4095,WORD(4096));c.expected="Invalid export ordinal";
  }
  for(const std::string table:{"functions","names","ordinals"}) {
    auto& c=add("export_truncated_"+table);cardinality_fixture(c,16,4096,4096);
    auto exports=get<IMAGE_EXPORT_DIRECTORY>(c.bytes,1024);
    // Exactly one byte less than the complete 4096-entry array is file-backed.
    if(table=="functions")exports.AddressOfFunctions=0x11800-4096*4+1;
    if(table=="names")exports.AddressOfNames=0x11800-4096*4+1;
    if(table=="ordinals")exports.AddressOfNameOrdinals=0x11800-4096*2+1;
    put(c.bytes,1024,exports);c.expected="RVA has no unique file-backed section";
  }
  {
    auto& c=add("manifest_final_duplicate");cardinality_fixture(c,16,33,33);
    auto m=get<LabManifestDeclaration>(c.bytes,count_descriptor);std::memcpy(m.ranges[15].begin,m.ranges[0].begin,64);put(c.bytes,count_descriptor,m);
    c.expected="Duplicate manifest export identifier";
  }
  {
    auto& c=add("manifest_final_overlap");cardinality_fixture(c,16,33,33);
    put(c.bytes,count_functions+30*4,DWORD(0x1000));put(c.bytes,count_functions+31*4,DWORD(0x1001));c.expected="Declared code ranges overlap";
  }
  {
    auto& c=add("manifest_final_missing_end");cardinality_fixture(c,16,33,33);
    auto rva=get<DWORD>(c.bytes,count_names+31*4);c.bytes[1024+rva-0x2000]='Z';c.expected="Required lab probe export is absent";
  }
  {
    auto& c=add("manifest_unused_at_15");cardinality_fixture(c,15,33,33);
    auto m=get<LabManifestDeclaration>(c.bytes,count_descriptor);m.ranges[15].begin[0]='X';put(c.bytes,count_descriptor,m);c.expected="Unused manifest declarations must be empty";
  }
  return result;
}
}
int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::logic_error("Expected evidence directory");
    const std::filesystem::path folder(argv[1]);std::filesystem::create_directories(folder);
    const auto tests=cases();
    if(tests.empty()||tests.size()>100)throw std::logic_error("Case budget exceeded");
    std::set<std::string> ids;unsigned failures=0;
    for(const auto& c:tests) {
      if(!ids.insert(c.id).second||c.bytes.size()>65536)throw std::logic_error("Invalid case identity or size");
      std::ofstream file(folder/(c.id+".bin"),std::ios::binary);
      file.write(reinterpret_cast<const char*>(c.bytes.data()),c.bytes.size());file.close();
      if(!file)throw std::logic_error("Cannot save fixture");
      std::string actual="ACCEPT";std::vector<LabImage::ResolvedRange> ranges;std::vector<LabImage::Span> spans;std::size_t mapped=0;
      try {
        LabImage image(c.bytes);
        if(c.mapping)mapped=image.offset(c.query,c.length);
        else {spans=image.executable_ranges();ranges=image.declared_ranges();if(image.preferred_base()!=0x140000000ULL)throw std::logic_error("Preferred base mismatch");}
      } catch(const std::runtime_error& error) {actual=error.what();}
      bool passed=actual==c.expected;
      if(passed&&actual=="ACCEPT") {
        if(c.mapping)passed=mapped==c.mapped;
        else if(!c.expected_ranges.empty()) {
          passed=ranges.size()==c.expected_ranges.size() && spans.size()==c.spans.size();
          for(std::size_t i=0;passed&&i<ranges.size();++i) {
            const auto& actual_range=ranges[i];const auto& expected=c.expected_ranges[i];
            passed=actual_range.name==expected.name && actual_range.rva==expected.rva && actual_range.expected==expected.expected;
          }
          for(std::size_t i=0;passed&&i<spans.size();++i)passed=spans[i].rva==c.spans[i].rva&&spans[i].size==c.spans[i].size;
        }
        else {
          passed=ranges.size()==2 && spans.size()==c.spans.size();
          if(passed)passed=ranges[0].name=="LabCodeProbe"&&ranges[0].rva==c.first_rva&&ranges[0].expected==std::vector<unsigned char>(c.first_length,0x90)&&ranges[1].name=="LabCodeSecondary"&&ranges[1].rva==c.second_rva&&ranges[1].expected==std::vector<unsigned char>(6,0x90);
          for(std::size_t i=0;passed&&i<spans.size();++i)passed=spans[i].rva==c.spans[i].rva&&spans[i].size==c.spans[i].size;
        }
      }
      std::cout<<"CASE\t"<<c.id<<'\t'<<(passed?"PASS":"FAIL")<<'\t'<<c.expected<<'\t'<<actual<<'\n';
      if(!passed)++failures;
    }
    std::cout<<"TOTAL\t"<<tests.size()<<'\t'<<failures<<'\n';return failures?1:0;
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
