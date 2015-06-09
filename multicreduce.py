#!/usr/bin/env python3

import sys
import os
import shutil
import argparse
import subprocess
import stat

from subprocess import *
from tempfile import *

parser = argparse.ArgumentParser(description='Multi creduce command')
parser.add_argument('--folder', dest = 'folder', help = 'Working folder', default = '.')
parser.add_argument('--creduce', dest = 'creduce', help = 'Path to creduce command', default = 'creduce')
parser.add_argument('--start-timeout', dest = 'start_timeout', help = 'Start timeout', default = 10)
parser.add_argument('--timeout-step', dest = 'timeout_step', help = 'Timeout step', default = 10)

args = parser.parse_args()

class BaseOperation:
    def __init__(self, command, pre_command, post_command):
        self.command = command
        self.pre_command = pre_command
        self.post_command = post_command

    def generate_output_name(self, name = None):
        self.output = name if name != None else self.get_temp()
        if self.original_output == None:
            self.original_output = self.output

    def get_temp(self):
        f = NamedTemporaryFile(delete = False, dir = os.path.abspath('tmp'))
        return f.name 

    def replace_tokens(self, command, inputs, output):
        for i in range(len(inputs)):
            t = '@%u' % i
            command.index(t)
            command = command.replace(t, inputs[i])
        t = '@$'
        command.index(t)
        command = command.replace(t, output)
        return command

    def build_commands(self, command):
        c = []
        if self.pre_command != None:
            c.append(self.pre_command(self))
        c.append(command)
        if self.post_command != None:
            c.append(self.post_command(self))

        return c

class ReduceOperation(BaseOperation):
    def __init__(self, command, input, pre_command = None, post_command = None):
        super().__init__(command, pre_command, post_command)
        self.input = input
        self.output = None
        self.original_output = None

    def build_command(self, script_argument = False):
        return self.build_commands(self.replace_tokens(self.command, [self.input] if not script_argument else ['$1'], self.output))

    def is_merge(self):
        return False

    def file_size(self):
        return os.stat(self.input).st_size

    def __str__(self):
        return 'reduce operation: %s (%s)' % (self.command, self.input)

class MergeOperation(BaseOperation):
    def __init__(self, command, inputs, name, pre_command = None, post_command = None):
        super().__init__(command, pre_command, post_command)
        self.inputs = inputs
        self.name = name
        self.original_output = None

    def build_command(self, script_argument = False):
        return self.build_commands(self.replace_tokens(self.command, list(map(lambda x: x.output, self.inputs)), self.output))

    def is_merge(self):
        return True

    def __str__(self):
        return 'merge operation: %s' % self.name

class MultiReduce:
    def __init__(self, reductions, merge):
        self.reductions = reductions
        self.merge = merge
        self.original_sizes = None
        self.script = None

    def calculate(self, reduction):
        worklist = []
        dependencies = []

        x = reduction
        while True:
            for m in self.merge:
                if x in m.inputs:
                    if not m in dependencies:
                        worklist.append(m)
                    dependencies.append(m)
            if len(worklist) == 0:
                break
            else:
                x = worklist.pop()
        return dependencies

    def set_original_names(self):
        for i in self.reductions + self.merge:
            if i.original_output != None:
                i.output = i.original_output

    def fix_temp_names(self):
        for i in self.merge + self.reductions:
            i.generate_output_name()

    def build_script(self, reduction = None):
        lines = ['#!/bin/bash', '']
        l = []
        # generate a temporary Makefile in case we reduce
        if reduction != None:
            dependencies = [reduction] + list(self.calculate(reduction))
            for d in range(len(dependencies)):
                t = 'temp%u' % d
                dependencies[d].generate_output_name('$' + t)
                lines.append(t + '=`mktemp --tmpdir=%s`' % os.path.abspath('tmp'))
            for d in dependencies:
                d = d.build_command(True)
                lines = lines + d
            return '\n'.join(lines)
        else:
            worklist = [self.merge[-1]]
            visited = set([self.merge[-1]])

            for i in worklist:
                # generate reduction commands just in case we do not
                # generate a Makefile for a reduction
                l += reversed(i.build_command())
                if i.is_merge():
                    for input in i.inputs:
                        if not input in visited:
                            worklist.append(input)

        lines = lines + list(reversed(l))
        return '\n'.join(lines)

    def print_file_stats(self):
        if self.original_sizes == None:
            self.original_sizes = {}
            for r in self.reductions:
                self.original_sizes[r] = r.file_size()

        print('=== Files ===')
        for r in self.reductions:
            s = r.file_size()
            o = self.original_sizes[r]
            if o == 0:
                o = 1
            print('%s: %u B (%2.2f%%)' % (r.input, s, 100 * s / o))
        print()

    def create_script_files(self):
        s = self.build_script()
        self.script = 'script_all.sh'
        with open(self.script, 'w') as f:
            f.write(s)

        for i, r in enumerate(self.reductions):
            self.set_original_names()
            s = self.build_script(r)
            r.script_file = 'script_%s.sh' % r.input
            with open(r.script_file, 'w') as f:
                f.write(s)
                f.close()
            st = os.stat(r.script_file)
            os.chmod(r.script_file, st.st_mode | stat.S_IEXEC)

    def wipe_tmp(self):
        t = 'tmp'
        if os.path.exists(t):
            shutil.rmtree(t)
        os.makedirs(t)

    def reduce(self):
        self.wipe_tmp()
        self.fix_temp_names()
        self.create_script_files()
        timeout = int(args.start_timeout)
        fnull = open(os.devnull, 'w')
        iteration = 0
        done = set()
        while True:
            if len(done) == len(self.reductions):
                print('Reduction has finished ;)')
                return

            self.wipe_tmp()

            iteration += 1
            for i, r in enumerate(multi.reductions):
                if r in done:
                    continue

                print('Running global script')
                check_output(['bash', self.script], stderr = fnull)
                print('Running %u. round with timeout: %u s: %s' % (iteration, timeout, r.script_file))
                multi.print_file_stats()
                try:
                    check_output(['creduce', r.script_file, r.input], timeout = timeout)
                    done.add(r)
                except subprocess.TimeoutExpired as e:
                    best = os.path.splitext(r.input)[0] + '.best'
                    shutil.copyfile(best, r.input)
                    print('Copy best file to the current one: %s' % best)
                    print('Output from creduce:')
                    print(e.output.decode(encoding = 'utf-8'))

            timeout += int(args.timeout_step)

### EXAMPLE ###

options = '-ftemplate-depth-128 -O3 -finline-functions -Wno-inline -Wall -g -pthread -O3 -flto=8 -c'
default_check = lambda x: 'if ! test $? = 0; then\nexit 1\nfi'

c1 = ReduceOperation('g++ ' + options + ' @0 -o @$', 'a.ii', post_command = default_check)
c2 = ReduceOperation('g++ ' + options + ' @0 -o @$', 'b.ii', post_command = default_check)
c3 = ReduceOperation('g++ ' + options + ' @0 -o @$', 'c.ii', post_command = default_check)
c4 = ReduceOperation('g++ ' + options + ' @0 -o @$', 'd.ii', post_command = default_check)
c5 = ReduceOperation('g++ ' + options + ' @0 -o @$', 'e.ii', post_command = default_check)

m1 = MergeOperation('ar cr @$ @0 @1 @2', [c3, c4, c5], 'ar', lambda x: 'rm -f ' + x.output)
m2 = MergeOperation('g++ -Wl,--start-group @0 @1 @2 -Wl,-Bstatic -lm -Wl,-Bdynamic -llzma -lbz2 -ltcmalloc_minimal -ldl -lboost_program_options -lSegFault -lz -lboost_thread -lboost_system -lrt -Wl,--end-group -g -pthread -O3 -flto=8 -D_GLIBCXX_USE_CXX11_ABI=0 2>&1 -o @$ | grep "internal compiler error"', [m1, c1, c2], 'link', post_command = default_check)

# run commands in a loop
if args.folder != None:
    os.chdir(args.folder)

multi = MultiReduce([c1, c2, c3, c4, c5], [m1, m2])
multi.reduce()

"""
for i in multi.reductions:
    print('dependencies for: %s', str(i))
    s = multi.calculate(i)
    for i in s:
        print('   %s' % str(i))
"""

