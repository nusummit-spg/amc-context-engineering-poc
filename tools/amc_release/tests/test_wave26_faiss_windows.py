"""Source patch and platform fsync behavior without a fake FAISS success claim."""
import ast
import pytest
from tools.amc_release.publication_patch26 import harden_faiss26, SourceDrift

SOURCE='''import os
from pathlib import Path

def finish(stage, dest):
            for f in stage.iterdir():
                with f.open("rb") as fh:
                    os.fsync(fh.fileno())
            try:
                os.rename(stage, dest)
            except FileExistsError:
                raise
            fd = os.open(dest.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
            return True
'''

def test_faiss_windows_guard_is_syntactically_valid():
    revised=harden_faiss26(SOURCE)
    assert 'W26_FAISS_WINDOWS_PORTABLE' in revised
    assert 'with f.open("rb+")' in revised
    assert 'if os.name != "nt":' in revised
    ast.parse(revised)


def test_patch_rejects_reapplication():
    with pytest.raises(SourceDrift):harden_faiss26(harden_faiss26(SOURCE))


def test_unsafe_drift_in_sync_anchor_rejected():
    with pytest.raises(SourceDrift):harden_faiss26(SOURCE.replace('with f.open("rb")','with f.open("r")'))


def test_windows_skips_directory_sync(tmp_path, monkeypatch):
    source=harden_faiss26(SOURCE)
    class FakeOS:
        name='nt';O_RDONLY=0
        def __init__(self): self.synced=[]
        def fsync(self,fd):self.synced.append(fd)
        def rename(self,src,dst):src.rename(dst)
    fake=FakeOS()
    env={'os':fake,'Path':__import__('pathlib').Path}
    exec(source.replace("import os\n", ""),env)
    src=tmp_path/'stage';src.mkdir();(src/'index.faiss').write_bytes(b'fake-index-bytes-not-a-real-FAISS-index')
    env['finish'](src,tmp_path/'published')
    assert len(fake.synced)==1
    assert (tmp_path/'published/index.faiss').is_file()


def test_linux_attempts_directory_sync(tmp_path):
    source=harden_faiss26(SOURCE)
    class FakeOS:
        name='posix';O_RDONLY=0
        def __init__(self): self.synced=[];self.opens=[]
        def fsync(self,fd):self.synced.append(fd)
        def rename(self,src,dst):src.rename(dst)
        def open(self,path,mode):self.opens.append(str(path));return 28
        def close(self,fd):pass
    fake=FakeOS()
    env={'os':fake,'Path':__import__('pathlib').Path}
    exec(source.replace("import os\n", ""),env)
    src=tmp_path/'stage';src.mkdir();(src/'index.faiss').write_bytes(b'not-a-real-index')
    env['finish'](src,tmp_path/'published')
    assert len(fake.synced)==2
    assert len(fake.opens)==1
