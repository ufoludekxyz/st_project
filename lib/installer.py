import os, stat

from .exceptions import *
from .disk import *
from .general import *
from .profiles import Profile

avail_locales = ['en_US.UTF-8', 'pl_PL.UTF-8']


class Installer():
    def __init__(self, partition, boot_partition, *, profile=None, mountpoint='/mnt', hostname='ArchInstalled'):
        self.profile = profile
        self.hostname = hostname
        self.mountpoint = mountpoint

        self.partition = partition
        self.boot_partition = boot_partition
        self.locale = 'en_US.UTF-8'

    def __enter__(self, *args, **kwargs):
        self.partition.mount(self.mountpoint)
        os.makedirs(f'{self.mountpoint}/boot', exist_ok=True)
        self.boot_partition.mount(f'{self.mountpoint}/boot')
        return self

    def __exit__(self, *args, **kwargs):
        if len(args) >= 2 and args[1]:
            raise args[1]
        log('Installation completed without any errors.', bg='black', fg='green')
        return True

    def pacstrap(self, *packages, **kwargs):
        if type(packages[0]) in (list, tuple): packages = packages[0]
        log(f'Installing packages: {packages}')

        if (sync_mirrors := sys_command('/usr/bin/pacman -Syy')).exit_code == 0:
            if (pacstrap := sys_command(f'/usr/bin/pacstrap {self.mountpoint} {" ".join(packages)}',
                                        **kwargs)).exit_code == 0:
                return True
            else:
                log(f'Could not strap in packages: {pacstrap.exit_code}')
        else:
            log(f'Could not sync mirrors: {sync_mirrors.exit_code}')

    def chroot(self, *cmd):
        return sys_command(f'/usr/bin/arch-chroot {self.mountpoint} {" ".join(cmd)}')

    def gen_fstab(self, flags='-Pu'):
        o = b''.join(sys_command(f'/usr/bin/genfstab -pU {self.mountpoint} >> {self.mountpoint}/etc/fstab'))
        if not os.path.isfile(f'{self.mountpoint}/etc/fstab'):
            raise RequirementError(
                f'Could not generate fstab\n{o}')
        return True

    def set_hostname(self, hostname=None):
        if not hostname: hostname = self.hostname
        with open(f'{self.mountpoint}/etc/hostname', 'w') as fh:
            fh.write(self.hostname + '\n')

    def set_locale(self, locale, encoding='UTF-8'):
        self.locale=locale
        with open(f'{self.mountpoint}/etc/locale.gen', 'a') as fh:
            fh.write(f'{locale} {encoding}\n')
        with open(f'{self.mountpoint}/etc/locale.conf', 'w') as fh:
            fh.write(f'LANG={locale}\n')
        self.chroot(f'locale-gen')

    def minimal_installation(self, locale=0):
        self.pacstrap('base base-devel linux linux-firmware efibootmgr vim networkmanager grub'.split(' '))
        self.gen_fstab()

        with open(f'{self.mountpoint}/etc/fstab', 'a') as fstab:
            fstab.write('\ntmpfs /tmp tmpfs defaults,noatime,mode=1777 0 0\n')

        self.set_hostname()
        self.set_locale(avail_locales[locale])
        self.chroot('systemctl enable NetworkManager')

        self.chroot(f'chmod 700 /root')
        return True

    def add_bootloader(self):
        log(f'Adding bootloader to {self.boot_partition}')
        if (install := self.chroot(f'grub-install --target=x86_64-efi '
                                   f'--efi-directory=/boot --bootloader-id=GRUB')).exit_code != 0:
            raise SysCallError(f'Grub installation error\n{install.exit_code}')
        if (config := self.chroot(f'grub-mkconfig -o /boot/grub/grub.cfg')).exit_code != 0:
            raise SysCallError(f'Grub configuration file generation failed\n{config.exit_code}')

    def add_additional_packages(self, *packages):
        self.pacstrap(*packages)

    def install_profile(self, profile):
        profile = Profile(self, profile)

        log(f'Installing profile {profile.name}')
        profile.install()

    def user_create(self, user: str, password=None):
        log(f'Creating user {user}')
        self.chroot(f'useradd -m -G wheel {user}')
        if password:
            self.user_set_pw(user, password)
        with open(f'{self.mountpoint}/etc/sudoers.d/{user}', 'w') as sudo:
            sudo.write(f'{user} ALL=(ALL) ALL\n')

    def user_set_pw(self, user, password):
        log(f'Setting password for {user}')
        self.chroot(f"sh -c \"echo '{user}:{password}' | chpasswd\"")
        pass


def locales():
    for i in range(len(avail_locales)):
        print(f'{i}: {avail_locales[i]}')
    return len(avail_locales)
