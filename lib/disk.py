import glob, re, os, json
from collections import OrderedDict
from .exceptions import *
from .general import *

ROOT_DIR_PATTERN = re.compile('^.*?/devices')
GPT = 0b00000001


class BlockDevice:
    def __init__(self, path, info):
        self.path = path
        self.info = info
        self.part_cache = OrderedDict()

    @property
    def device(self):
        """
		Returns the actual device-endpoint of the BlockDevice.
		If it's a loop-back-device it returns the back-file,
		If it's a ATA-drive it returns the /dev/X device
		And if it's a crypto-device it returns the parent device
		"""
        if not 'type' in self.info: raise DiskError(f'Could not locate backplane info for "{self.path}"')

        if self.info['type'] == 'loop':
            for drive in json.loads(b''.join(sys_command(f'losetup --json', hide_from_log=True)).decode('UTF_8'))[
                'loopdevices']:
                if not drive['name'] == self.path: continue

                return drive['back-file']
        elif self.info['type'] == 'disk':
            return self.path
        elif self.info['type'] == 'crypt':
            if not 'pkname' in self.info: raise DiskError(
                f'A crypt device ({self.path}) without a parent kernel device name.')
            return f"/dev/{self.info['pkname']}"

    @property
    def partitions(self):
        o = b''.join(sys_command(f'partprobe {self.path}'))

        o = b''.join(sys_command(f'/usr/bin/lsblk -J {self.path}'))
        if b'not a block device' in o:
            raise DiskError(f'Can not read partitions off something that isn\'t a block device: {self.path}')

        if not o[:1] == b'{':
            raise DiskError(f'Error getting JSON output from:', f'/usr/bin/lsblk -J {self.path}')

        r = json.loads(o.decode('UTF-8'))
        if len(r['blockdevices']) and 'children' in r['blockdevices'][0]:
            root_path = f"/dev/{r['blockdevices'][0]['name']}"
            for part in r['blockdevices'][0]['children']:
                part_id = part['name'][len(os.path.basename(self.path)):]
                if part_id not in self.part_cache:
                    self.part_cache[part_id] = Partition(root_path + part_id, part_id=part_id, size=part['size'])

        return {k: self.part_cache[k] for k in sorted(self.part_cache)}

    @property
    def partition(self):
        all_partitions = self.partitions
        return [all_partitions[k] for k in all_partitions]

    def __repr__(self, *args, **kwargs):
        return f"BlockDevice({self.device})"

    def __getitem__(self, key, *args, **kwargs):
        if not key in self.info:
            raise KeyError(f'{self} does not contain information: "{key}"')
        return self.info[key]


class Partition:
    def __init__(self, path, part_id=None, size=-1, filesystem=None, mountpoint=None):
        if not part_id: part_id = os.path.basename(path)
        self.path = path
        self.part_id = part_id
        self.mountpoint = mountpoint
        self.filesystem = filesystem
        self.size = size

    def __repr__(self, *args, **kwargs):
        return f'Partition(path={self.path}, fs={self.filesystem}, mounted={self.mountpoint})'

    def format(self, filesystem):
        log(f'Formatting {self} -> {filesystem}')
        if filesystem == 'fat32':
            o = b''.join(sys_command(f'/usr/bin/mkfs.vfat -F32 {self.path}'))
            if (b'mkfs.fat' not in o and b'mkfs.vfat' not in o) or b'command not found' in o:
                raise DiskError(f'Could not format {self.path} with {filesystem} because: {o}')
            self.filesystem = 'fat32'
        elif filesystem == 'ext4':
            if (handle := sys_command(f'/usr/bin/mkfs.ext4 -F {self.path}')).exit_code != 0:
                raise DiskError(f'Could not format {self.path} with {filesystem} because: {b"".join(handle)}')
            self.filesystem = 'fat32'
        else:
            raise DiskError(f'Fileformat {filesystem} is not yet implemented.')
        return True

    def find_parent_of(self, data, name, parent=None):
        if data['name'] == name:
            return parent
        elif 'children' in data:
            for child in data['children']:
                if (parent := self.find_parent_of(child, name, parent=data['name'])):
                    return parent

    def mount(self, target, fs=None, options=''):
        if not self.mountpoint:
            log(f'Mounting {self} to {target}')
            if not fs:
                if not self.filesystem: raise DiskError(
                    f'Need to format (or define) the filesystem on {self} before mounting.')
                fs = self.filesystem
            if sys_command(f'/usr/bin/mount {self.path} {target}').exit_code == 0:
                self.mountpoint = target
                return True


class Filesystem:
    def __init__(self, blockdevice, mode=GPT):
        self.blockdevice = blockdevice
        self.mode = mode

    def __enter__(self, *args, **kwargs):
        if self.mode == GPT:
            if sys_command(f'/usr/bin/parted -s {self.blockdevice.device} mklabel gpt', ).exit_code == 0:
                return self
            else:
                raise DiskError(f'Problem setting the partition format to GPT:',
                                f'/usr/bin/parted -s {self.blockdevice.device} mklabel gpt')
        else:
            raise DiskError(f'Unknown mode selected to format in: {self.mode}')

    def __exit__(self, *args, **kwargs):
        if len(args) >= 2 and args[1]:
            raise args[1]
        b''.join(sys_command(f'sync'))
        return True

    def raw_parted(self, string: str):
        x = sys_command(f'/usr/bin/parted -s {string}')
        o = b''.join(x)
        return x

    def parted(self, string: str):
        """
		Performs a parted execution of the given string

		:param string: A raw string passed to /usr/bin/parted -s <string>
		:type string: str
		"""
        return self.raw_parted(string).exit_code

    def use_entire_disk(self, prep_mode=None):
        self.add_partition('primary', start='1MiB', end='513MiB', format='fat32')
        self.set_name(0, 'EFI')
        self.set(0, 'boot on')
        self.set(0, 'esp on')
        self.add_partition('primary', start='513MiB', end='100%', format='ext4')

    def add_partition(self, type, start, end, format=None):
        log(f'Adding partition to {self.blockdevice}')
        if format:
            return self.parted(f'{self.blockdevice.device} mkpart {type} {format} {start} {end}') == 0
        else:
            return self.parted(f'{self.blockdevice.device} mkpart {type} {start} {end}') == 0

    def set_name(self, partition: int, name: str):
        return self.parted(f'{self.blockdevice.device} name {partition + 1} "{name}"') == 0

    def set(self, partition: int, string: str):
        return self.parted(f'{self.blockdevice.device} set {partition + 1} {string}') == 0


def all_disks(*args, **kwargs):
    if not 'partitions' in kwargs: kwargs['partitions'] = False
    drives = OrderedDict()
    for drive in json.loads(b''.join(
            sys_command(f'lsblk --json -l -n -o path,size,type,mountpoint,label,pkname', *args, **kwargs,
                        hide_from_log=True)).decode('UTF_8'))['blockdevices']:
        if not kwargs['partitions'] and drive['type'] == 'part': continue

        drives[drive['path']] = BlockDevice(drive['path'], drive)
    return drives

def select_disk(dict_o_disks):
    drives = sorted(list(dict_o_disks.keys()))
    if len(drives) > 1:
        for index, drive in enumerate(drives):
            print(f"{index}: {drive} ({dict_o_disks[drive]['size'], dict_o_disks[drive].device, dict_o_disks[drive]['label']})")
        drive = input('Select one of the above disks (by number or full path): ')
        if drive.isdigit():
            drive = dict_o_disks[drives[int(drive)]]
        elif drive in dict_o_disks:
            drive = dict_o_disks[drive]
        else:
            raise DiskError(f'Selected drive does not exist: "{drive}"')
        return drive

    raise DiskError('select_disk() requires a non-empty dictionary of disks to select from.')
