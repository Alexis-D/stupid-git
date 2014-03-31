#!/usr/bin/env python3.4

# 3.4 because of pathlib, codecs
import codecs
import hashlib
import os
import pathlib
import struct
import sys
import time
import zlib


INDEX_HEADER_FMT = '!4c2I'
INDEX_BEFORE_SHA1_FMT = '!10I'
INDEX_FLAGS_FMT = '!H'


def find_git_dir():
    def find_git_dir_rec(directory):
        # TODO(adaboville): deal with $GIT_DIR
        if (directory / '.git').is_dir():
            return directory / '.git'
        elif len(directory.parts) == 1:  # root & not a git dir
            raise  # TODO(adaboville): handle this properly

        return find_git_dir_rec(directory.parent)

    return find_git_dir_rec(pathlib.Path.cwd())


def find_repo_root():
    return find_git_dir().parent


def get_object(object_type, content):
    length = str(len(content)).encode('ascii')
    return b''.join([
        object_type.encode('ascii'),
        b' ',
        length,
        b'\0',
        content,
    ])


def hash_single_object(git_object):
    return hashlib.sha1(git_object).hexdigest()


def hash_single_object_bytes(git_object):
    return hashlib.sha1(git_object).digest()


def write_object(sha1, git_object):
    # TODO(adaboville): should compute sha1 here
    git_dir = find_git_dir()
    target_dir = git_dir / 'objects' / sha1[:2]

    try:
        target_dir.mkdir(parents=True)
    except FileExistsError:
        pass

    with (target_dir / sha1[2:]).open('wb') as f:
        compressed = zlib.compress(git_object)
        f.write(compressed)


def read_object(sha1):
    git_dir = find_git_dir()

    with (git_dir / 'objects' / sha1[:2] / sha1[2:]).open('rb') as f:
        return zlib.decompress(f.read())


def get_content(git_object):
    return git_object.split(b'\0', maxsplit=1)[1]


def get_type(git_object):
    return git_object\
        .split(b'\0', maxsplit=1)[0].split(b' ')[0].decode('ascii')


def read_index():
    # https://www.kernel.org/pub/software/scm/git/docs/technical/pack-format.txt
    index_file = find_git_dir() / 'index'

    if not index_file.is_file():
        return

    with index_file.open('rb') as f:
        content = f.read()

    header = struct.unpack(INDEX_HEADER_FMT, content[:12])
    assert b''.join(header[:4]) == b'DIRC'  # signature
    version, entry_count = header[4:]
    assert version == 2  # don't handle version 3

    # check file integrity
    sha1 = content[-hashlib.sha1().digest_size:]
    m = hashlib.sha1(content[:-hashlib.sha1().digest_size])
    assert m.digest() == sha1

    start_offset = struct.calcsize(INDEX_HEADER_FMT)

    for _ in range(entry_count):
        sha1_start = start_offset + struct.calcsize(INDEX_BEFORE_SHA1_FMT)
        flags_start = sha1_start + hashlib.sha1().digest_size
        entry_path_start = flags_start + struct.calcsize(INDEX_FLAGS_FMT)

        stat = struct.unpack(INDEX_BEFORE_SHA1_FMT,
                             content[start_offset:sha1_start])
        sha1 = codecs.encode(content[sha1_start:flags_start],
                             'hex').decode('ascii')
        flags = struct.unpack(INDEX_FLAGS_FMT,
                              content[flags_start:entry_path_start])
        path = content[entry_path_start:content.find(b'\0', entry_path_start)]

        yield (path, sha1)

        entry_length = (entry_path_start + len(path) + 1) - start_offset
        if entry_length % 8 != 0:
            # TODO(adaboville): assert that padding bytes are null
            entry_length += 8 - (entry_length % 8)

        start_offset += entry_length

    # TODO(adaboville): parse extensions (at the very least the required ones)


def write_index(index):
    # this function is highly wrong/inefficient, but that's also one of the
    # least interesting (w/ read_index)
    index_file = find_git_dir() / 'index'
    content = struct.pack(INDEX_HEADER_FMT, b'D', b'I', b'R', b'C', 2,
                          len(index))

    for path in sorted(index):
        stat = os.stat(path)
        # not fully compliant with the spec
        mode = 0b1000 if os.stat(path) == os.lstat(path) else 0b1010
        mode <<= 3
        mode <<= 9
        mode |= 0o755  # this is overly wrong (especially for links)

        with open(path, 'rb') as f:
            file_content = f.read()

        git_object = get_object('blob', file_content)
        object_sha1 = hash_single_object_bytes(git_object)

        flags = 0b1000000000000000
        path_length = (len(path) if len(path) else 0xFFF)
        flags |= path_length

        entry = struct.pack(
            INDEX_BEFORE_SHA1_FMT,
            int(stat.st_ctime),
            # nost_ctime_nsec on MacOS afaict
            int((stat.st_ctime % 1) * 10 ** 6),
            int(stat.st_mtime),
            int((stat.st_mtime % 1) * 10 ** 6),
            stat.st_dev,
            stat.st_ino,
            mode,
            stat.st_uid,
            stat.st_gid,
            stat.st_size & (2 ** 32 - 1))

        # highly inefficient, I know :) see io.BufferedRandom for a better way
        # to write this function
        content += entry
        content += object_sha1
        content += struct.pack(INDEX_FLAGS_FMT, flags)
        content += path
        content += b'\0' * (8 - len(path) % 8)

    sha1 = hashlib.sha1(content).digest()
    content += sha1

    with index_file.open('wb') as f:
        f.write(content)


def cat_file(parsed):
    git_object = read_object(parsed.object)

    if parsed.show == 'pretty':
        # this isn't pretty since get_content returns raw content
        print(get_content(git_object))
    elif parsed.show == 'type':
        print(get_type(git_object))


def commit_tree(parsed):
    message = sys.stdin.read()

    tree = b'tree ' + parsed.tree.encode('ascii')
    # should read this from gitconfig but whatever
    author = b'author stupid git <sg.py> '\
             + time.strftime('%s %z').encode('ascii')
    parent = b'\n'.join((b'parent ' + parent.encode('ascii') for parent in
                        parsed.parents))
    committer = b'author stupid git <sg.py> '\
                + time.strftime('%s %z').encode('ascii')

    if parent:
        commit = b'\n'.join([tree, parent, author, committer,
                            b'\n' + message.encode('utf-8')])
    else:
        commit = b'\n'.join([tree, author, committer,
                            b'\n' + message.encode('utf-8')])

    git_object = get_object('commit', commit)
    sha1 = hash_single_object(git_object)
    write_object(sha1, git_object)
    print(sha1)


def hash_object(parsed):
    for filename in parsed.files:
        with open(filename, 'rb') as f:
            content = f.read()

        git_object = get_object(parsed.type, content)
        sha1 = hash_single_object(git_object)

        if parsed.w:
            write_object(sha1, git_object)

        print(sha1)


def init(parsed):
    try:
        # TODO(adaboville): deal with $GIT_DIR
        git_dir = pathlib.Path.cwd() / '.git'

        for directory in ['branches', 'objects', 'refs/heads']:
            (git_dir / directory).mkdir(parents=True)

        with (git_dir / 'HEAD').open('w') as f:
            f.write('ref: refs/heads/master\n')

    except FileExistsError:
        pass


def update_index(parsed):
    index = dict(read_index())

    def add_file(filename):
        path = bytes(filename.resolve().relative_to(find_repo_root()))

        if parsed.add or path in index:
            with filename.open('rb') as f:
                content = f.read()

            git_object = get_object('blob', content)
            index[path] = hash_single_object(git_object)
        else:
            # TODO(adaboville): print error message
            pass  # if new file, must specify --add

    for path in parsed.files:
        path = pathlib.Path(path)

        # TODO(adaboville): support --remove
        if path.is_file():
            add_file(path)
        else:
            for path in path.glob('**/*'):
                add_file(path)

    write_index(index)


def update_ref(parsed):
    git_dir = find_git_dir()

    def update(ref, value):
        path = git_dir / ref

        with path.open('a+') as f:
            f.seek(0)
            ref = f.readline().strip()

            if ref.startswith('ref: '):
                update(ref.split(' ')[1].strip(), value)
            else:
                # the file is a sha, the size is right (yes that's gross)
                f.seek(0)
                f.write(value)
                f.write('\n')

    update(parsed.ref, parsed.value)


def write_tree(parsed):
    index = dict(read_index())
    content = b''

    for path, sha1 in index.items():
        content += b'100644 blob ' + path + b'\0' + bytearray.fromhex(sha1)

    git_object = get_object('tree', content)
    sha1 = hash_single_object(git_object)
    write_object(sha1, git_object)
    print(sha1)


if __name__ == '__main__':
    import argparse

    commands = {
        'cat-file': cat_file,
        'commit-tree': commit_tree,
        'init': init,
        'hash-object': hash_object,
        'update-index': update_index,
        'update-ref': update_ref,
        'write-tree': write_tree,
    }

    parser = argparse.ArgumentParser(description='sg -- stupid git')
    subparsers = parser.add_subparsers(dest='action')

    cat_file_parser = subparsers.add_parser('cat-file')
    group = cat_file_parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-t', dest='show', action='store_const', const='type')
    group.add_argument('-p', dest='show', action='store_const', const='pretty')
    cat_file_parser.add_argument('object')

    commit_tree_parser = subparsers.add_parser('commit-tree')
    commit_tree_parser.add_argument('-p', dest='parents', action='append',
                                    default=[])
    commit_tree_parser.add_argument('tree')

    hash_object_parser = subparsers.add_parser('hash-object')
    hash_object_parser.add_argument('-t', dest='type', default='blob')
    hash_object_parser.add_argument('-w', action='store_true', default=False)
    hash_object_parser.add_argument('files', metavar='file',
                                    nargs=argparse.REMAINDER)

    init_parser = subparsers.add_parser('init')

    update_index_parser = subparsers.add_parser('update-index')
    group = update_index_parser.add_mutually_exclusive_group()
    group.add_argument('--add', dest='add', action='store_true',
                       default=False)
    # group.add_argument('--remove', dest='remove', action='store_true',
    #                    default=False)
    update_index_parser.add_argument('files', metavar='file',
                                     nargs=argparse.REMAINDER)

    update_ref_parser = subparsers.add_parser('update-ref')
    update_ref_parser.add_argument('ref')
    update_ref_parser.add_argument('value')

    write_tree_parser = subparsers.add_parser('write-tree')

    parsed = parser.parse_args(sys.argv[1:])

    if parsed.action in commands:
        commands[parsed.action](parsed)
    else:
        pass  # TODO(adaboville): deal with that
