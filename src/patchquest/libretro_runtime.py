"""Minimal software-video libretro adapter; no core is bundled or downloaded.

ABI reference: https://github.com/libretro/libretro-common/blob/master/include/libretro.h
This independently implemented client uses public ABI declarations, not copied
emulator code. Run native cores only in the bounded worker, after explicit setup.
"""
import array
import ctypes as C
import sys
from pathlib import Path
from .runtime import BUTTONS,Frame,sha


class SystemInfo(C.Structure):
    _fields_=[('name',C.c_char_p),('version',C.c_char_p),('extensions',C.c_char_p),('fullpath',C.c_bool),('block_extract',C.c_bool)]


class GameInfo(C.Structure):
    _fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]


class Variable(C.Structure):
    _fields_=[('key',C.c_char_p),('value',C.c_char_p)]


def unpack_pixels(raw,width,height,pitch,pixel_format):
    """Convert software callback pixels without scaling or overlays."""
    size=4 if pixel_format==1 else 2
    if pixel_format not in (0,1,2) or width<1 or height<1 or width>2048 or height>2048 or pitch<width*size or len(raw)!=pitch*height:
        raise ValueError('Unsupported software frame')
    out=bytearray(width*height*3);dest=0
    for y in range(height):
        row=raw[y*pitch:y*pitch+width*size]
        if pixel_format==1:
            for x in range(0,len(row),4):out[dest:dest+3]=bytes((row[x+2],row[x+1],row[x]));dest+=3
        else:
            values=array.array('H',row)
            for v in values:
                if pixel_format==2:r,g,b=(v>>11)&31,(v>>5)&63,v&31;g=(g<<2)|(g>>4)
                else:r,g,b=(v>>10)&31,(v>>5)&31,v&31;g=(g<<3)|(g>>2)
                out[dest:dest+3]=bytes(((r<<3)|(r>>2),g,(b<<3)|(b>>2)));dest+=3
    return Frame(width,height,bytes(out))


class Libretro:
    """Trusted explicitly selected core; isolated files, not a security sandbox.

    Basic joypad, software video, native states and isolated battery saves.
    No audio analysis, debugger, WRAM writes, downloads or desktop automation.
    """
    def __init__(self,core,expected_sha256):
        if sys.byteorder!='little':raise ValueError('This adapter supports little-endian hosts only')
        self.path=Path(core).resolve();self.digest=sha(self.path.read_bytes())
        if self.digest!=expected_sha256:raise ValueError('Emulator executable hash differs')
        self.dll=C.CDLL(str(self.path));self.initialized=False;self.loaded=False;self.frame=None;self.pixel_format=0;self.error=None
        self.buttons=set();self.callbacks=[];self.strings=[];self.defaults={};self.polls=0;self.frames=0;self.video_calls=0;self.input_reads=0;self.pressed_reads=0
        def signature(name,result,args):
            f=getattr(self.dll,name);f.restype=result;f.argtypes=args;return f
        if signature('retro_api_version',C.c_uint,[])()!=1:raise ValueError('Unsupported libretro ABI')
        self.info=SystemInfo();signature('retro_get_system_info',None,[C.POINTER(SystemInfo)])(C.byref(self.info))
        signature('retro_init',None,[]);signature('retro_deinit',None,[]);signature('retro_run',None,[])
        signature('retro_load_game',C.c_bool,[C.POINTER(GameInfo)]);signature('retro_unload_game',None,[])
        signature('retro_unserialize',C.c_bool,[C.c_void_p,C.c_size_t]);signature('retro_serialize_size',C.c_size_t,[])
        signature('retro_serialize',C.c_bool,[C.c_void_p,C.c_size_t]);signature('retro_set_controller_port_device',None,[C.c_uint,C.c_uint])
        signature('retro_get_memory_size',C.c_size_t,[C.c_uint]);signature('retro_get_memory_data',C.c_void_p,[C.c_uint])
        self.initial_save='fresh core defaults; no existing saves imported'
        def callback(name,result,args,method):
            typ=C.CFUNCTYPE(result,*args);f=typ(method);self.callbacks.append(f);signature(name,None,[typ])(f)
        callback('retro_set_environment',C.c_bool,[C.c_uint,C.c_void_p],self.environment)
        callback('retro_set_video_refresh',None,[C.c_void_p,C.c_uint,C.c_uint,C.c_size_t],self.video)
        callback('retro_set_input_poll',None,[],self.poll)
        callback('retro_set_input_state',C.c_int16,[C.c_uint,C.c_uint,C.c_uint,C.c_uint],self.input)
        callback('retro_set_audio_sample',None,[C.c_int16,C.c_int16],lambda *_:None)
        callback('retro_set_audio_sample_batch',C.c_size_t,[C.c_void_p,C.c_size_t],lambda _,frames:frames)

    def describe(self):
        return dict(kind='actual_emulator',adapter='libretro-software-v1',name=self.info.name.decode(),version=self.info.version.decode(),sha256=self.digest,
                    options={'core_options':{k.decode():v.decode() for k,v in sorted(self.defaults.items())},'controller':'port 0 joypad','initial_sram':self.initial_save,'audio':'discarded; not inspected'},
                    capabilities=['software_frames','joypad_frame_steps','core_native_states','isolated_save_ram'],unsupported=['hardware_video','audio_evidence','debugger','desktop_frontend_state_compatibility'])

    def environment(self,command,data):
        try:
            if command==10:
                fmt=C.cast(data,C.POINTER(C.c_int))[0]
                if fmt not in (0,1,2):return False
                self.pixel_format=fmt;return True
            if command in (9,31):
                if not hasattr(self,'work_bytes'):return False
                C.cast(data,C.POINTER(C.c_char_p))[0]=self.work_bytes;return True
            if command==3:C.cast(data,C.POINTER(C.c_bool))[0]=True;return True
            if command==17:C.cast(data,C.POINTER(C.c_bool))[0]=False;return True
            if command==16:
                values=C.cast(data,C.POINTER(Variable))
                for i in range(1000):
                    v=values[i]
                    if not v.key:break
                    if v.value and b'; ' in v.value:self.defaults[v.key]=v.value.split(b'; ',1)[1].split(b'|',1)[0]
                return True
            if command==15:
                v=C.cast(data,C.POINTER(Variable));value=self.defaults.get(v[0].key)
                if value is None:return False
                v[0].value=value;return True
            if command==7:self.error='Core requested shutdown';return True
            # These notifications do not grant extra interfaces or permissions.
            # Contentless operation is announced by 18; this runner still loads a ROM.
            # Frame-time callback 21 is unsupported, not a passive notification.
            if command in (11,18,35,36,37):return True
            return False
        except Exception as error:self.error=str(error);return False

    def video(self,data,width,height,pitch):
        try:
            self.video_calls+=1
            if not data:return # Explicit duplicate frame retains the prior image.
            if data==C.c_void_p(-1).value:raise ValueError('Hardware framebuffer unsupported')
            if not 0<width<=2048 or not 0<height<=2048 or not 0<pitch<=16384:raise ValueError('Frame bounds')
            self.frame=(C.string_at(data,pitch*height),width,height,pitch,self.pixel_format)
        except Exception as error:self.error=str(error)

    def poll(self):self.polls+=1

    def input(self,port,device,index,key):
        self.input_reads+=1
        value=int(port==0 and device==1 and index==0 and key<len(BUTTONS) and BUTTONS[key] in self.buttons)
        self.pressed_reads+=value
        return value

    def observations(self):
        return dict(core_run_calls=self.frames,video_callbacks=self.video_calls,input_polls=self.polls,input_queries=self.input_reads,pressed_button_queries=self.pressed_reads,
                    timing='Core frame calls, not wall-clock gameplay pacing; audio discarded')

    def load(self,rom,workdir):
        if self.initialized:raise ValueError('Core already initialized')
        work=Path(workdir).resolve();work.mkdir(parents=True,exist_ok=False);self.work_bytes=str(work).encode();self.strings.append(self.work_bytes)
        self.dll.retro_init();self.initialized=True
        self.buffer=C.create_string_buffer(rom);path=work/'input.rom';path.write_bytes(rom);self.rom_path=str(path).encode();self.strings.append(self.rom_path)
        info=GameInfo(self.rom_path,C.cast(self.buffer,C.c_void_p),len(rom),None)
        self.loaded=bool(self.dll.retro_load_game(C.byref(info)))
        if not self.loaded:raise ValueError('Core rejected input ROM')
        self.dll.retro_set_controller_port_device(0,1)
        if self.error:raise ValueError(self.error)

    def step(self,buttons):
        self.buttons=set(buttons);self.dll.retro_run();self.frames+=1
        if self.error:raise ValueError(self.error)
        if self.frame is None:raise ValueError('Core did not produce a software frame')
        return unpack_pixels(*self.frame)

    def restore(self,raw):
        data=C.create_string_buffer(raw)
        if not self.dll.retro_unserialize(data,len(raw)):raise ValueError('Core rejected state')
        self.initial_save='native state; battery-save persistence not established'

    def _save_ram_region(self):
        if not self.loaded:raise ValueError('No loaded content for save RAM')
        size=self.dll.retro_get_memory_size(0) # RETRO_MEMORY_SAVE_RAM; never system RAM.
        if not 0<size<=16*1024*1024:raise ValueError('Save RAM unavailable or unsupported size')
        pointer=self.dll.retro_get_memory_data(0)
        if not pointer:raise ValueError('Save RAM pointer unavailable')
        return pointer,size

    def save_ram(self):
        pointer,size=self._save_ram_region()
        return C.string_at(pointer,size)

    def memory_size(self,region):
        """Size of an explicitly selected readable region; zero means unavailable.

        Call between frame steps on the core's owning worker thread. Region
        offsets are byte offsets in the returned block, not CPU addresses.
        Availability does not establish any game-renderer instrumentation.
        """
        key=self._read_memory_key(region)
        size=self.dll.retro_get_memory_size(key)
        if type(size) is not int or not 0<=size<=16*1024*1024:
            raise ValueError('Read-only memory region size unsupported')
        return size

    def _read_memory_key(self,region):
        if type(region) is not str or region not in ('system_ram','video_ram'):
            raise ValueError('Read-only memory requires system_ram or video_ram')
        if not self.loaded:raise ValueError('No loaded content for read-only memory')
        return 2 if region=='system_ram' else 3

    def read_memory(self,region,offset,length):
        """Copy a bounded immutable slice without exposing or retaining a pointer.

        No writes, bank mapping, synchronization or interpretation are provided.
        The trusted core must be idle on this thread for the complete call.
        """
        key=self._read_memory_key(region)
        if type(offset) is not int or offset<0 or type(length) is not int or not 1<=length<=1024*1024:
            raise ValueError('Read-only memory range unsupported')
        size=self.memory_size(region)
        if not size or offset>size or length>size-offset:
            raise ValueError('Read-only memory range unavailable')
        pointer=self.dll.retro_get_memory_data(key)
        if not pointer:raise ValueError('Read-only memory pointer unavailable')
        return C.string_at(pointer+offset,length)

    def load_save_ram(self,raw):
        if self.frames:raise ValueError('Save RAM import requires fresh boot before frame execution')
        pointer,size=self._save_ram_region()
        if not isinstance(raw,bytes) or len(raw)!=size:raise ValueError('Save RAM size differs')
        C.memmove(pointer,raw,size)
        self.initial_save={'kind':'explicit_save_ram','sha256':sha(raw),'bytes':size}

    def save_state(self):
        size=self.dll.retro_serialize_size()
        if not 0<size<=64*1024*1024:raise ValueError('State size unsupported')
        data=C.create_string_buffer(size)
        if not self.dll.retro_serialize(data,size):raise ValueError('Core rejected state capture')
        return data.raw

    def close(self):
        if self.loaded:self.dll.retro_unload_game();self.loaded=False
        if self.initialized:self.dll.retro_deinit();self.initialized=False
