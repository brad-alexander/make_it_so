#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Make it so uses a yaml config file to apply configuration to the target server
"""

import os
import argparse
import logging
import warnings
import hashlib
import shutil

import yaml
import paramiko

warnings.filterwarnings(action='ignore', module='.*paramiko.*')
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def conn_ssh(hostname, config):
    """
    Create ssh and sftp client connection.
    Input:
    hostname
    config - dic with key of username and password

    Returns ssh client and sftp client connection
    """
    username = config["username"]
    password = config["password"]
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=hostname, port=22, username=username, password=password)
        sftp_client = ssh_client.open_sftp()
        log.info("ssh_client and sftp_client connection established")
        return ssh_client, sftp_client
    except Exception as e:
        print(e)


def package_install(connection, packages, config):
    """
    Input:
    ssh connection
    config - dic with key of ensure with value of install or remove

    Returns stdout
    """
    install_action = config["application"][0].get("ensure")
    if 1 in packages.values() and install_action == 'install':
        stdin, stdout, stderr = connection.exec_command("apt-get -qq -y {} {}".format(install_action,
                                                                                      ' '.join(packages.keys())))
        exit_status = stdout.channel.recv_exit_status()
        log.info("Installed {} exit status {}".format(' '.join(packages.keys()), exit_status))
        return stdout
    elif 0 in packages.values() and install_action == 'remove':
        stdin, stdout, stderr = connection.exec_command("apt-get -qq -y {} {}".format(install_action,
                                                                                      ' '.join(packages.keys())))
        exit_status = stdout.channel.recv_exit_status()
        log.info("Removed {} exit status {}".format(' '.join(packages.keys()), exit_status))
        return stdout


def check_package_install(connection, config):
    """ Checks if a system package is installed
    Input:
    ssh connection
    config - dic with key of name and optionally add_package. name is the main package to be installed.
        add_package is a list of packages.

    Returns package_status a dic with {'package_name':  exit code of check if installed}
    """
    packages = config["application"][0].get("add_package")
    packages.extend([config["application"][0].get("name")])

    package_status = {}
    for package in packages:
        stdin, stdout, stderr = connection.exec_command('dpkg -l {}| grep -q ^ii'.format(package))
        package_status[package] = int(stdout.channel.recv_exit_status())
    log.info("Package status {}".format(package_status))
    return package_status


def service_trigger(connection, config):
    """ Restarts the main application
    Input:
    ssh connection
    config - dic with key of name to be restarted

    Returns stdout of command
    """
    service = (config["application"][0].get("name"))
    stdin, stdout, stderr = connection.exec_command('service {} restart '.format(service))
    exit_status = stdout.channel.recv_exit_status()
    log.info("Service {} restarted, exit status {}".format(service, exit_status))
    return stdout


def file_data(ssh_connection, sftp_connection, config):
    """
    Updates target files on server

    Input:
    ssh_connection = ssh_client connection
    sftp_connection = sftp connection
    config = dictonary to be used to find templates and params to be updated

    Returns reload_trigger True/False to be used to trigger a restart of the main service

    """
    template = config["application"][1].get("templates")
    os.mkdir('/tmp/make_it_so')
    for template in template:
        if template.get('template_file') and template.get('location'):
            local_file_name, local_md5 = stage_local_file(template)
            des_file_name, des_md5, des_chmod = test_des_file(ssh_connection, template)
            if template.get('chmod') and template.get('group') and template.get('owner'):
                local_chmod = template.get('chmod')+template.get('owner')+template.get('group')
            else:
                local_chmod = des_chmod

            if (des_md5 == local_md5) and (local_chmod == des_chmod):
                reload_trigger = False
                return reload_trigger
            else:
                copy_file(sftp_client=sftp_connection,
                          src=local_file_name,
                          des=des_file_name
                          )
                chmod_file(connection=ssh_connection,
                           chmod=template.get('chmod'),
                           owner=template.get('owner'),
                           group=template.get('group'),
                           file=des_file_name)
                reload_trigger = True
                return reload_trigger


def chmod_file(connection, chmod, owner, group, file):
    """
    Changes the group/owner and perms of target file

    Input:
    connection = ssh_client connection
    chmod = 3 number chmod
    owner = owner of file
    group = group of file

    Returns stdout of both commands

    """
    mod_stdin, mod_stdout, mod_stderr = connection.exec_command("chmod {} {}".format(chmod, file))
    exit_status = mod_stdout.channel.recv_exit_status()
    log.info("Changed {} mode to {} exit status {}".format(file, chmod, exit_status))

    own_stdin, own_stdout, own_stderr = connection.exec_command("chown {}:{} {}".format(owner, group, file))
    exit_status = own_stdout.channel.recv_exit_status()
    log.info("Changed {} owner/group to {} {} exit status {}".format(file, owner, group, exit_status))
    return mod_stdout, own_stdout


def copy_file(sftp_client, src, des):
    """
    copies a local file to a remote server

    Input:
    sftp_client = sft_client connection
    src = local file
    des = destination to put the file

    """
    try:
        sftp_client.put(localpath=src, remotepath=des)
        log.info("Copied {} at {}".format(src, des))
    except Exception as e:
        print(e)


def test_des_file(connection, dic_template):
    """
    Tests the destination file for file params and md5sum

    Input:
    connection = ssh_client connection
    dic_template = dictonary which includes location of file to test

    Returns file name, md5sum and perms and ownership
    """
    des_file = dic_template.get('location')
    md5_stdin, md5_stdout, md5_stderr = connection.exec_command('md5sum  {}'.format(des_file),
                                                                get_pty=True)
    chmod_stdin, chmod_stdout, chmod_stderr = connection.exec_command('stat --format ""%a%U%G""  {}'.format(des_file),
                                                                      get_pty=True)
    if md5_stdout.channel.recv_exit_status() == 1:
        return des_file, False, False
    else:
        m_lines = md5_stdout.readlines()
        for line in m_lines:
            des_md5 = line.split(" ")
        c_lines = chmod_stdout.readlines()
        for line in c_lines:
            des_chmod = line
        return des_file, des_md5[0], des_chmod.rstrip()


def stage_local_file(dic_template):
    """
    Reads in a local file and writes a new file with updated string sub
    """
    local_file = '/tmp/make_it_so/{}'.format(dic_template.get('template_file'))
    with open('templates/{}'.format(dic_template.get('template_file')), "rt") as fin:
        with open(local_file, "wt") as fout:
            param_items = dic_template.get('params')[0]
            for key, value in param_items.items():
                for line in fin:
                    fout.write(line.replace("__{}__".format(key), value))
    return local_file, md5(local_file)


def md5(fname):
    """
    Reads in a local file and returns the md5sum
    """
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def yaml_config(yaml_file):
    """
    Reads in a yaml file and returns the yaml as a dic
    """
    try:
        with open(yaml_file) as f:
            datamap = yaml.safe_load(f)
            return datamap
    except FileNotFoundError:
        log.error("Your file {} is not there".format(yaml_file))


def parser():
    """
    Argparse
    """
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--host', required=True, help='host to apply config')
    arg_parser.add_argument('--config', required=True, help='config to apply', default=False)
    args = arg_parser.parse_args()

    return args


def main():
    """
    Main Function
    """
    args = parser()
    # creates the tmp directory early on
    shutil.rmtree('/tmp/make_it_so', ignore_errors=True)
    config = yaml_config(yaml_file=args.config)
    ssh_client, sftp_client = conn_ssh(hostname=args.host, config=config)
    packages = check_package_install(connection=ssh_client, config=config)
    package_install(connection=ssh_client, packages=packages, config=config)
    reload_trigger = file_data(ssh_connection=ssh_client, sftp_connection=sftp_client, config=config)
    if reload_trigger is True:
        service_trigger(connection=ssh_client, config=config)
    ssh_client.close()
    # removes the tmp directory late
    shutil.rmtree('/tmp/make_it_so', ignore_errors=True)


if __name__ == '__main__':
    main()
