"""Pinned randomizer format round-trips and seed-save isolation, without game data."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    tools = ROOT / "integrations/randomizer/tools"
    if not tools.is_dir():
        print("randomizer: skipped (initialize the optional submodule)")
        return
    if sys.version_info < (3, 14):
        print("randomizer: skipped (Python 3.14+ required)")
        return
    sys.path.insert(0, str(tools))
    import bymlw
    import nxfmt
    import launcher
    sample = {"text": "Longshot 日本", "flags": [True, False, None], "number": -42,
              "wide": bymlw.U64(2 ** 63 + 7), "unsigned": bymlw.U32(2 ** 32 - 1),
              "binary": bymlw.Bin(b"synthetic"), "real": bymlw.F64(1.125)}
    for endian in ("<", ">"):
        restored, metadata = bymlw.loads(bymlw.dumps(sample, endian=endian))
        assert metadata == {"endian": endian, "version": 7}
        assert restored == sample
        assert type(restored["wide"]) is bymlw.U64
        assert type(restored["unsigned"]) is bymlw.U32
    files = {"Test/one.byml": bymlw.dumps(sample), "Test/two.txt": b"fixture"}
    assert nxfmt.parse_sarc(bymlw.build_sarc(files)) == files
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        launcher.GAME = root / "game"
        launcher.SAVES = root / "seed-saves"
        account = launcher.GAME / "user/save/account"
        (account / "slot_00").mkdir(parents=True)
        (account / "slot_00/progress.sav").write_bytes(b"original-progress")
        for name in ("account.sav", "option.sav"):
            (account / name).write_bytes(b"synthetic-settings")
        seed_a, seed_b = launcher.prepare_saves(123), launcher.prepare_saves(456)
        assert seed_a != seed_b
        assert (seed_a / "save/account/option.sav").read_bytes() == b"synthetic-settings"
        assert not (seed_a / "save/account/slot_00").exists()
        (seed_a / "keep.sav").write_bytes(b"seed progress")
        assert launcher.prepare_saves(123) == seed_a and (seed_a / "keep.sav").read_bytes() == b"seed progress"
        assert (account / "slot_00/progress.sav").read_bytes() == b"original-progress"
    print("randomizer: typed BYML/SARC round-trips and per-seed save isolation passed; seed beatability is not tested")


if __name__ == "__main__":
    main()
