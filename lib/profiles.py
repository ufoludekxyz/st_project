import json
import os

from archinstall import *


class Profile:
    def __init__(self, installer, name):
        self.name = name
        self.installer = installer
        self.packages = ''
        self.commands = []

    def load_instructions(self):
        if os.path.exists(f'./archinstall/profiles/{self.name}.json'):
            with open(f'./archinstall/profiles/{self.name}.json', 'r') as fh:
                return json.load(fh)

        raise ProfileError(f'No such profile ({self.name}) was found')

    def install(self):
        instructions = self.load_instructions()
        if 'packages' in instructions:
            self.packages = instructions['packages']
        if 'commands' in instructions:
            self.commands = instructions['commands']
        self.installer.pacstrap(self.packages.split(' '))
        for cmd in self.commands:
            if (cmd_exec := self.installer.chroot(cmd)).exit_code != 0:
                raise SysCallError(f'Could not execute command {cmd_exec.exit_code}')
