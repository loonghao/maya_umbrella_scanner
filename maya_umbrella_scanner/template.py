# Template for the runner script.
RUNNER_TEMPLATE = """
import hashlib
import json
import os
import sys

try:
    string_types = (basestring,)
    text_type = unicode
except NameError:
    string_types = (str,)
    text_type = str


def to_text(value):
    if isinstance(value, text_type):
        return value
    return value.decode(sys.getfilesystemencoding() or 'utf-8', 'replace')


def to_maya_path(value):
    value = to_text(value)
    if sys.version_info[0] >= 3:
        return value
    try:
        return value.encode('ascii')
    except UnicodeEncodeError:
        raise RuntimeError('Python 2 Maya cleanup does not support non-ASCII scene paths safely.')


def resolved_path(value):
    value = to_text(value)
    return os.path.normcase(os.path.abspath(os.path.expanduser(value)))


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_cleanup_contract(infected_file, report_path, report_sha256, target):
    with open(report_path, 'rb') as stream:
        report_bytes = stream.read()
    if hashlib.sha256(report_bytes).hexdigest() != report_sha256:
        raise RuntimeError('Approved scan report changed before Maya startup.')
    report = json.loads(report_bytes)
    normalized_target = ensure_no_reparse_components(target)
    matches = [
        item for item in report.get('targets', [])
        if isinstance(item, dict)
        and isinstance(item.get('path'), string_types)
        and resolved_path(item['path']) == normalized_target
    ]
    if len(matches) != 1:
        raise RuntimeError('Approved scan report target changed before Maya startup.')
    expected = matches[0].get('infected_sha256_before')
    if not isinstance(expected, dict):
        raise RuntimeError('Approved scan report hashes are invalid.')
    normalized_expected = {}
    for path, digest in expected.items():
        normalized_path = ensure_no_reparse_components(path)
        if normalized_path in normalized_expected:
            raise RuntimeError('Approved scan report contains duplicate normalized paths.')
        normalized_expected[normalized_path] = digest
    with open(infected_file, 'rb') as stream:
        current_paths = [
            ensure_no_reparse_components(line.decode('utf-8-sig', 'replace').strip())
            for line in stream
            if line.strip()
        ]
    if len(set(current_paths)) != len(current_paths) or set(current_paths) != set(normalized_expected):
        raise RuntimeError('Infected paths changed before Maya startup.')
    current_hashes = {path: sha256_file(path) for path in current_paths}
    if current_hashes != normalized_expected:
        raise RuntimeError('Infected file hashes changed before Maya startup.')
    return current_paths, normalized_expected


def is_reparse_point(path):
    if os.name == 'nt':
        import ctypes

        get_attributes = ctypes.windll.kernel32.GetFileAttributesW
        get_attributes.argtypes = [ctypes.c_wchar_p]
        get_attributes.restype = ctypes.c_uint32
        attributes = get_attributes(to_text(path))
        if attributes == 0xFFFFFFFF:
            raise RuntimeError('Unable to inspect backup path attributes: {path}'.format(path=path))
        return bool(attributes & 0x400)
    try:
        attributes = getattr(os.lstat(path), 'st_file_attributes', 0)
    except OSError:
        return False
    return os.path.islink(path) or bool(attributes & 0x400)


def ensure_no_reparse_components(value):
    normalized = resolved_path(value)
    drive, tail = os.path.splitdrive(normalized)
    current = drive + os.sep if drive else os.sep
    tail = tail.replace('\\\\', os.sep).replace('/', os.sep)
    for component in [part for part in tail.split(os.sep) if part]:
        current = os.path.join(current, component)
        if not os.path.lexists(current):
            raise RuntimeError('Approved path component no longer exists: {path}'.format(path=current))
        if is_reparse_point(current):
            raise RuntimeError('Approved cleanup path contains a symlink or junction: {path}'.format(
                path=current
            ))
    return normalized


def file_identity(path):
    if os.name != 'nt':
        status = os.stat(path)
        return status.st_dev, status.st_ino

    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ('file_attributes', wintypes.DWORD),
            ('creation_time', wintypes.FILETIME),
            ('last_access_time', wintypes.FILETIME),
            ('last_write_time', wintypes.FILETIME),
            ('volume_serial_number', wintypes.DWORD),
            ('file_size_high', wintypes.DWORD),
            ('file_size_low', wintypes.DWORD),
            ('number_of_links', wintypes.DWORD),
            ('file_index_high', wintypes.DWORD),
            ('file_index_low', wintypes.DWORD),
        ]

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    handle = create_file(to_text(path), 0, 0x7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise RuntimeError('Unable to open backup path for identity verification: {path}'.format(path=path))
    close_handle = ctypes.windll.kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = wintypes.BOOL
    try:
        information = ByHandleFileInformation()
        get_information = ctypes.windll.kernel32.GetFileInformationByHandle
        get_information.argtypes = [ctypes.c_void_p, ctypes.POINTER(ByHandleFileInformation)]
        get_information.restype = wintypes.BOOL
        if not get_information(handle, ctypes.byref(information)):
            raise RuntimeError('Unable to verify backup path identity: {path}'.format(path=path))
        return (
            information.volume_serial_number,
            information.file_index_high,
            information.file_index_low,
        )
    finally:
        close_handle(handle)


def approved_backup_path(path):
    ensure_no_reparse_components(path)
    source_parent = ensure_no_reparse_components(os.path.dirname(path))
    backup_directory = os.path.join(source_parent, '_virus')
    if not os.path.lexists(backup_directory):
        try:
            os.mkdir(backup_directory)
        except OSError:
            if not os.path.lexists(backup_directory):
                raise
    ensure_no_reparse_components(backup_directory)
    if not os.path.isdir(backup_directory):
        raise RuntimeError('Backup directory must be a regular local directory: {path}'.format(
            path=backup_directory
        ))
    resolved_directory = resolved_path(backup_directory)
    if os.path.dirname(resolved_directory) != source_parent or os.path.basename(resolved_directory) != '_virus':
        raise RuntimeError('Backup directory escaped the scene directory: {path}'.format(
            path=backup_directory
        ))
    return os.path.join(backup_directory, os.path.basename(path))


def verify_approved_backup(path, backup, expected_digest):
    ensure_no_reparse_components(path)
    if sha256_file(path) != expected_digest:
        raise RuntimeError('Infected file hash changed before backup verification: {path}'.format(path=path))
    expected_backup = resolved_path(os.path.join(os.path.dirname(path), '_virus', os.path.basename(path)))
    if resolved_path(backup) != expected_backup:
        raise RuntimeError('Approved backup path changed before save: {path}'.format(path=backup))
    ensure_no_reparse_components(backup)
    if not os.path.isfile(backup):
        raise RuntimeError('Approved backup is not a regular file: {path}'.format(path=backup))
    if file_identity(path) == file_identity(backup):
        raise RuntimeError('Approved backup is not independent from its source scene: {path}'.format(
            path=backup
        ))
    if sha256_file(backup) != expected_digest:
        raise RuntimeError('Approved backup no longer contains the approved scene bytes: {path}'.format(
            path=backup
        ))
    return backup


def ensure_approved_backup(path, expected_digest):
    import shutil

    ensure_no_reparse_components(path)
    if sha256_file(path) != expected_digest:
        raise RuntimeError('Infected file hash changed before backup staging: {path}'.format(path=path))
    backup = approved_backup_path(path)
    if os.path.lexists(backup):
        return verify_approved_backup(path, backup, expected_digest)

    descriptor = None
    created = False
    try:
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        destination = os.fdopen(descriptor, 'wb')
        descriptor = None
        try:
            with open(path, 'rb') as source:
                shutil.copyfileobj(source, destination, 1024 * 1024)
        finally:
            destination.close()
        shutil.copystat(path, backup)
        approved_backup_path(path)
        verify_approved_backup(path, backup, expected_digest)
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                os.remove(backup)
            except OSError:
                pass
        raise
    return backup


def collected_external_files(defender):
    files = list(defender.collector.malicious_files)
    files.extend(defender.collector.infected_files)
    return sorted(set(resolved_path(path) for path in files))


def inspect_approved_scenes(cmds, maya_paths):
    from maya_umbrella import maya_funs
    from maya_umbrella.defender import MayaVirusDefender

    references = []
    external_files = []
    for path in maya_paths:
        ensure_no_reparse_components(path)
        defender = MayaVirusDefender(auto_fix=False)
        try:
            maya_funs.open_maya_file(path)
            ensure_no_reparse_components(path)
            defender.collect()
            references.extend(defender.collector.infected_reference_files)
            external_files.extend(collected_external_files(defender))
        finally:
            cmds.file(new=True, force=True)
    return (
        sorted(set(resolved_path(path) for path in references)),
        sorted(set(external_files)),
    )


def reject_unapproved_scope(references, external_files):
    if references:
        raise RuntimeError(
            'Infected Maya references require a separate approved scan: {references}'.format(
                references=json.dumps(references, ensure_ascii=True)
            )
        )
    if external_files:
        raise RuntimeError(
            'Infected external Maya or Python files require a separate explicit remediation scope: '
            '{files}'.format(files=json.dumps(external_files, ensure_ascii=True))
        )


def clean_approved_scenes(cmds, maya_paths, approved_hashes):
    from maya_umbrella import maya_funs
    from maya_umbrella.defender import MayaVirusDefender

    for path in maya_paths:
        ensure_no_reparse_components(path)
        normalized_path = resolved_path(path)
        expected_digest = approved_hashes[normalized_path]
        defender = MayaVirusDefender(auto_fix=False)
        try:
            maya_funs.open_maya_file(path)
            ensure_no_reparse_components(path)
            if sha256_file(path) != expected_digest:
                raise RuntimeError('Infected file hash changed before cleanup: {path}'.format(path=path))
            defender.collect()
            reject_unapproved_scope(
                [resolved_path(item) for item in defender.collector.infected_reference_files],
                collected_external_files(defender),
            )
            scene_has_issues = bool(
                defender.collector.infected_nodes or defender.collector.infected_script_jobs
            )
            if scene_has_issues:
                backup = ensure_approved_backup(path, expected_digest)
                ensure_no_reparse_components(path)
                if sha256_file(path) != expected_digest:
                    raise RuntimeError('Infected file hash changed before mutation: {path}'.format(path=path))
                # The broad upstream fix also deletes user-profile and Maya-install
                # files. Keep this approved operation strictly scene-scoped.
                defender.virus_cleaner.fix_infected_nodes()
                defender.virus_cleaner.fix_script_jobs()
                ensure_no_reparse_components(path)
                if sha256_file(path) != expected_digest:
                    raise RuntimeError('Infected file hash changed before save: {path}'.format(path=path))
                verify_approved_backup(path, backup, expected_digest)
                cmds.file(save=True, force=True)
        finally:
            cmds.file(new=True, force=True)


if __name__ == '__main__':
    infected_file, report_path, report_sha256, target = [to_text(value) for value in sys.argv[1:5]]
    approved_paths, approved_hashes = verify_cleanup_contract(infected_file, report_path, report_sha256, target)
    # Bypass the upstream ASCII manifest decoder, while rejecting paths that
    # Python 2 Maya cannot safely open and save before Maya is initialized.
    maya_paths = [to_maya_path(path) for path in approved_paths]

    from maya_umbrella import maya_funs

    cleanup_error = None
    maya_funs.maya_standalone.initialize()
    try:
        cmds = maya_funs.cmds
        infected_references, external_files = inspect_approved_scenes(cmds, maya_paths)
        reject_unapproved_scope(infected_references, external_files)
        clean_approved_scenes(cmds, maya_paths, approved_hashes)
    except Exception as exc:
        cleanup_error = exc
    finally:
        maya_funs.maya_standalone.uninitialize()
    if cleanup_error is not None:
        raise cleanup_error

"""
