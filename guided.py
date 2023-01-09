import archinstall, getpass, time

# Unmount and close previous runs
archinstall.sys_command(f'umount -R /mnt', surpress_errors=True)

hard_drive = archinstall.select_disk(archinstall.all_disks())
hostname = input('Desired hostname for the installation: ')
if len(hostname) == 0: hostname = 'ArchInstall'
ll = int(archinstall.locales())
locale = int(input('Desired locale: '))
if not locale or locale > ll:
    locale = 0
while root_pw := getpass.getpass(prompt='Enter root password (leave blank for no password): '):
    root_pw_verification = getpass.getpass(prompt='And one more time for verification: ')
    if root_pw != root_pw_verification:
        archinstall.log(' * Passwords did not match * ', bg='black', fg='red')
        continue
    break

users = {}
while 1:
    new_user = input('Any additional users to install (leave blank for no users): ')
    if not len(new_user.strip()):
        break
    new_user_passwd = getpass.getpass(prompt=f'Password for user {new_user}: ')
    new_user_passwd_verify = getpass.getpass(prompt=f'Enter password again for verification: ')
    if new_user_passwd != new_user_passwd_verify:
        archinstall.log(' * Passwords did not match * ', bg='black', fg='red')
        continue

    users[new_user] = new_user_passwd

profile = input('Any particular profile you want to install: ')
packages = input('Additional packages aside from base (space separated): ').split(' ')

print(f' ! Formatting {hard_drive} in 5...')
time.sleep(1)
print(f' ! Formatting {hard_drive} in 4...')
time.sleep(1)
print(f' ! Formatting {hard_drive} in 3...')
time.sleep(1)
print(f' ! Formatting {hard_drive} in 2...')
time.sleep(1)
print(f' ! Formatting {hard_drive} in 1...')
time.sleep(1)


def perform_installation(device, boot_partition):
    with archinstall.Installer(device, boot_partition=boot_partition, hostname=hostname) as installation:
        archinstall.prerequisit_check()
        if installation.minimal_installation(locale=locale):
            installation.add_bootloader()

            if len(packages) and packages[0] != '':
                installation.add_additional_packages(packages)

            if len(profile.strip()):
                installation.install_profile(profile)

            for user, password in users.items():
                installation.user_create(user, password)

            if root_pw:
                installation.user_set_pw('root', root_pw)


with archinstall.Filesystem(hard_drive, archinstall.GPT) as fs:
    fs.use_entire_disk('ext4')
    hard_drive.partition[0].format('fat32')
    hard_drive.partition[1].format('ext4')
    perform_installation(hard_drive.partition[1], hard_drive.partition[0])
