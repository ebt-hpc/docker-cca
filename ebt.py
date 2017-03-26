#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
  A driver script for CCA/EBT container image

  Copyright 2013-2017 RIKEN

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
'''

__author__ = 'Masatomo Hashimoto <m.hashimoto@riken.jp>'

import os
import sys
import time
from datetime import datetime, timedelta
from subprocess import Popen, call
from threading import Thread
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

IMAGE_NAME = 'ebtxhpc/cca'

#

DATA_DIR_NAME = '_EBT_'
DEFAULT_SRV_PORT = 18000

CCA_HOME = '/opt/cca'
CCA_VAR = '/var/lib/cca'
PROJS_DIR = CCA_VAR+'/projects'
CCA_LOG_DIR = '/var/log/cca'
WWW_DIR = '/var/www'
SRV_CMD = '/usr/local/bin/supervisord'


CONTAINER_CMD = 'docker'

TIMEOUT = 5
BUFSIZE = 0 # unbuffered

STAT_NAME = 'status'
LOG_DIR_NAME = 'log'

### timezone

TZ = None

if time.timezone != 0:
    SIGN = '+' if time.timezone > 0 else '-'

    STDOFFSET = timedelta(seconds=-time.timezone)
    if time.daylight:
        DSTOFFSET = timedelta(seconds=-time.altzone)
    else:
        DSTOFFSET = STDOFFSET

    dt = datetime.now()
    tt = (dt.year, dt.month, dt.day,
          dt.hour, dt.minute, dt.second,
          dt.weekday(), 0, 0)
    stamp = time.mktime(tt)
    tt = time.localtime(stamp)

    isdst = tt.tm_isdst > 0

    tzname = None
    offset = 0

    if isdst:
        tzname = time.tzname[1]
        offset = DSTOFFSET
    else:
        tzname = time.tzname[0]
        offset = STDOFFSET

    TZ = '%s%s%s' % (tzname, SIGN, offset)

###

def progress(proc, stat_path, timeout=TIMEOUT):
    stat_mtime = None

    print('\nmonitoring thread started.')

    while True:
        try:
            st = os.stat(stat_path)
            if st.st_mtime != stat_mtime and st.st_size > 0:
                with open(stat_path, 'r') as f:
                    mes = f.read()
                    print('[%s]' % mes)

                stat_mtime = st.st_mtime

        except OSError as e:
            pass

        if proc.poll() is not None:
            break

    proc.wait()
    if proc.returncode > 0:
        print('execution failed: %s' % proc.returncode)


def check_path(dpath):
    dpath = os.path.abspath(dpath)

    if not os.path.exists(dpath):
        print('"%s": not found' % dpath)
        return None

    return dpath

def get_proj_id(dpath):
    return os.path.basename(dpath)

def get_proj_path(dpath):
    proj_id = get_proj_id(dpath)
    proj_path = '%s/%s' % (PROJS_DIR, proj_id)
    return proj_path


def run_cmd(subcmd_name, dpath, mem, dry_run=False):
    dpath = check_path(dpath)

    if dpath == None:
        return

    dest_root = os.path.join(dpath, DATA_DIR_NAME)
    if os.path.exists(dest_root):
        print('You are about to overwrite "%s".' % dest_root)
        while True:
            a = raw_input('Do you want to proceed (y/n)? ')
            if a == 'y':
                break
            elif a == 'n':
                return

    else:
        try:
            os.makedirs(dest_root)
        except Exception as e:
            print('"%s": faild to create: %s' % (dest_root, e))
            return

    proj_path = get_proj_path(dpath)

    subcmd_path = '%s/%s' % (CCA_HOME, subcmd_name)
    subcmd = subcmd_path
    subcmd += ' -m %d' % mem
    subcmd += ' %s' % proj_path

    log_dir = os.path.join(dest_root, LOG_DIR_NAME)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception as e:
            print('"%s": faild to create: %s' % (log_dir, e))
            return

    vol_opt = '-v %s:%s' % (dpath, proj_path)
    vol_opt += ' -v %s:%s' % (log_dir, CCA_LOG_DIR)

    run_cmd = '%s run' % CONTAINER_CMD
    run_cmd += ' --rm'
    run_cmd += ' -t'

    if TZ:
        run_cmd += ' -e "TZ=%s"' % TZ

    run_cmd += ' %s' % vol_opt
    run_cmd += ' %s %s' % (IMAGE_NAME, subcmd)

    stat_path = os.path.join(dest_root, STAT_NAME)

    print(run_cmd)

    if not dry_run:

        if os.path.exists(stat_path):
            #print('removing "%s"...' % stat_path)
            os.remove(stat_path)

        try:
            proc = Popen(run_cmd, bufsize=BUFSIZE, shell=True,
                         universal_newlines=True)

            th = Thread(target=progress, args=(proc, stat_path))
            th.start()
            th.join()

        except (KeyboardInterrupt, SystemExit):
            print('interrupted.')

        except OSError as e:
            print('execution failed: %s' % e)


def run_tv_srv(dpath, port=DEFAULT_SRV_PORT, dry_run=False):
    subcmd_name = 'treeview'
    dpath = check_path(dpath)

    if dpath == None:
        return

    dest_root = os.path.join(dpath, DATA_DIR_NAME)

    mongo_path = os.path.join(dest_root, 'mongo')
    mongo_db_path = os.path.join(mongo_path, 'db')
    try:
        if not os.path.exists(mongo_db_path):
            os.makedirs(mongo_db_path)
    except Exception as e:
        print('"%s": failed to create: %s' % (mongo_db_path, e))
        return

    proj_id = get_proj_id(dpath)
    proj_path = get_proj_path(dpath)

    outline_path = os.path.join(dest_root, 'outline', proj_id)
    metrics_path = os.path.join(dest_root, 'metrics', proj_id)
    target_path = os.path.join(dest_root, 'target', proj_id)
    topic_path = os.path.join(dest_root, 'topic')
    readme_links_path = os.path.join(dest_root, 'readme_links')
    data_path_base = WWW_DIR+'/outline/treeview/'

    log_dir = os.path.join(dpath, DATA_DIR_NAME, LOG_DIR_NAME)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception as e:
            print('"%s": faild to create: %s' % (log_dir, e))
            return

    vol_opt = '-v %s:%s' % (dpath, proj_path)
    vol_opt += ' -v %s:%s' % (log_dir, CCA_LOG_DIR)
    vol_opt += ' -v %s:%s' % (outline_path, data_path_base+'outline/'+proj_id)
    vol_opt += ' -v %s:%s' % (metrics_path, data_path_base+'metrics/'+proj_id)
    vol_opt += ' -v %s:%s' % (target_path, data_path_base+'target/'+proj_id)
    vol_opt += ' -v %s:%s' % (topic_path, data_path_base+'topic')
    vol_opt += ' -v %s:%s' % (readme_links_path, data_path_base+'readme_links')
    vol_opt += ' -v %s:%s' % (mongo_path, CCA_VAR+'/mongo')

    name = '%s_%s' % (subcmd_name, proj_id)

    port_opt = '-p %d:80' % port

    run_cmd = '%s run' % CONTAINER_CMD
    run_cmd += ' -d'
    run_cmd += ' --rm'
    run_cmd += ' %s' % port_opt
    run_cmd += ' --name %s' % name

    if TZ:
        run_cmd += ' -e "TZ=%s"' % TZ

    run_cmd += ' %s' % vol_opt
    run_cmd += ' %s %s' % (IMAGE_NAME, SRV_CMD)

    print(run_cmd)
    print('\nport=%d' % port)

    if not dry_run:
        try:
            call(run_cmd, shell=True)
        except OSError as e:
            print('execution failed: %s' % e)


def stop_tv_srv(dpath, dry_run=False):
    subcmd_name = 'treeview'
    dpath = check_path(dpath)

    if dpath == None:
        return

    name = '%s_%s' % (subcmd_name, os.path.basename(dpath))

    stop_cmd = '%s stop %s' % (CONTAINER_CMD, name)

    print(stop_cmd)

    if not dry_run:
        try:
            call(stop_cmd, shell=True)
        except OSError as e:
            print('execution failed: %s' % e)
    

def opcount(args):
    run_cmd('opcount', args.proj_dir, args.mem, dry_run=args.dry_run)

def outline(args):
    run_cmd('outline', args.proj_dir, args.mem, dry_run=args.dry_run)

def treeview_start(args):
    run_tv_srv(args.proj_dir, port=args.port, dry_run=args.dry_run)

def treeview_stop(args):
    stop_tv_srv(args.proj_dir, dry_run=args.dry_run)


def main():
    parser = ArgumentParser(description='CCA/EBT driver',
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-m', '--mem', dest='mem', metavar='GB',
                        choices=[2, 4, 8, 16, 32, 48, 64],
                        help='available memory (GB)', default=4)

    parser.add_argument('-n', '--dry-run', dest='dry_run', action='store_true',
                        help='only print container commands')

    subparsers = parser.add_subparsers(title='subcommands')

    parser_opcount = subparsers.add_parser('opcount',
                                           formatter_class=ArgumentDefaultsHelpFormatter)
    parser_opcount.add_argument('proj_dir', type=str, metavar='DIR',
                                help='directory that subject programs reside')
    parser_opcount.set_defaults(func=opcount)

    parser_outline = subparsers.add_parser('outline',
                                           formatter_class=ArgumentDefaultsHelpFormatter)
    parser_outline.add_argument('proj_dir', type=str, metavar='DIR',
                                help='directory that subject programs reside')
    parser_outline.set_defaults(func=outline)

    parser_tv = subparsers.add_parser('treeview')

    subparsers_tv = parser_tv.add_subparsers(title='subsubcommands')

    parser_tv_start = subparsers_tv.add_parser('start',
                                               formatter_class=ArgumentDefaultsHelpFormatter)
    parser_tv_start.add_argument('proj_dir', type=str, metavar='DIR',
                                 help='directory that subject programs reside')
    parser_tv_start.add_argument('-p', '--port', dest='port', default=DEFAULT_SRV_PORT,
                                 metavar='PORT', type=int,
                                 help='service port number')
    parser_tv_start.set_defaults(func=treeview_start)

    parser_tv_stop = subparsers_tv.add_parser('stop',
                                              formatter_class=ArgumentDefaultsHelpFormatter)
    parser_tv_stop.add_argument('proj_dir', type=str, metavar='DIR',
                                 help='directory that subject programs reside')
    parser_tv_stop.set_defaults(func=treeview_stop)


    args = parser.parse_args()

    args.func(args)


if __name__ == '__main__':
    main()
