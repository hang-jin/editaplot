"""Fail-closed public-release audit for the EditaPlot source repository.

The verifier is intentionally standard-library only.  It reads the Git index and
the worktree, never edits either, and ignores unrelated untracked files.  Normal
release/CI use is strict: every required release file must already be tracked.
``--candidate`` exists only so a maintainer can validate the explicitly required
new files before staging them; it does not discover or scan other untracked files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MAX_PNG_TEXT_BYTES = 65_536


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    path: str | None = None

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": self.message}
        if self.path is not None:
            result["path"] = self.path
        return result


class ReleaseAudit:
    def __init__(self, root: Path, policy: dict[str, Any], *, candidate: bool = False) -> None:
        self.root = root
        self.policy = policy
        self.candidate = candidate
        self.findings: list[Finding] = []
        self.tracked_modes: dict[str, str] = {}
        self.tracked_object_ids: dict[str, str] = {}
        self.git_object_format = "sha1"
        self.audited_paths: set[str] = set()
        self.total_bytes = 0

    def fail(self, code: str, message: str, path: str | None = None) -> None:
        self.findings.append(Finding(code=code, message=message, path=path))

    def run(self) -> dict[str, Any]:
        self._load_tracked_files()
        self._verify_index_matches_worktree()
        self._add_candidate_required_files()
        self._verify_required_files_are_tracked()
        self._verify_paths_and_contents()
        self._verify_license_and_notice()
        self._verify_dependency_lock()
        self._verify_gallery()
        self._verify_palettes()
        self._verify_runtime_manifest()
        self._verify_asset_provenance()
        return {
            "schema_version": 1,
            "policy": str(self.policy.get("policy_name", "public release")),
            "ok": not self.findings,
            "mode": "candidate" if self.candidate else "strict",
            "tracked_file_count": len(self.tracked_modes),
            "audited_file_count": len(self.audited_paths),
            "audited_total_bytes": self.total_bytes,
            "errors": [finding.as_dict() for finding in self.findings],
        }

    def _load_tracked_files(self) -> None:
        git = shutil.which("git")
        if git is None:
            raise RuntimeError("Git is required for a tracked-file release audit.")
        completed = subprocess.run(  # noqa: S603 - resolved executable and fixed read-only arguments
            [git, "-c", "core.quotepath=false", "ls-files", "--stage", "-z"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"git ls-files failed: {detail}")
        format_result = subprocess.run(  # noqa: S603 - fixed read-only Git query
            [git, "rev-parse", "--show-object-format"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if format_result.returncode != 0:
            detail = format_result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"git object-format query failed: {detail}")
        self.git_object_format = format_result.stdout.decode("ascii").strip()
        if self.git_object_format not in {"sha1", "sha256"}:
            raise RuntimeError(f"Unsupported Git object format: {self.git_object_format}")
        for raw_entry in completed.stdout.split(b"\0"):
            if not raw_entry:
                continue
            try:
                metadata, raw_path = raw_entry.split(b"\t", 1)
                mode, object_id, stage = metadata.decode("ascii").split(" ", 2)
                path = raw_path.decode("utf-8", errors="surrogateescape").replace("\\", "/")
            except (ValueError, UnicodeError) as exc:
                raise RuntimeError("Could not parse a Git index entry.") from exc
            if stage != "0":
                self.fail("unmerged_index", "The Git index contains an unmerged entry.", path)
            if path in self.tracked_modes:
                self.fail("duplicate_tracked_path", "The Git index repeats this path.", path)
            self.tracked_modes[path] = mode
            self.tracked_object_ids[path] = object_id
            self.audited_paths.add(path)

    def _add_candidate_required_files(self) -> None:
        if not self.candidate:
            return
        for path in self.policy.get("required_tracked", []):
            if path not in self.tracked_modes and (self.root / path).is_file():
                self.audited_paths.add(path)

    def _verify_index_matches_worktree(self) -> None:
        if self.candidate:
            return
        git = shutil.which("git")
        if git is None:
            raise RuntimeError("Git is required for a tracked-file release audit.")
        completed = subprocess.run(  # noqa: S603 - resolved executable and fixed read-only arguments
            [git, "diff", "--quiet", "--no-ext-diff", "--"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 1:
            self.fail(
                "index_worktree_mismatch",
                "Tracked worktree content differs from the staged index; stage or revert it before audit.",
            )
        elif completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"git diff failed: {detail}")
        for path, object_id in sorted(self.tracked_object_ids.items()):
            if self.tracked_modes.get(path) not in {"100644", "100755"}:
                continue
            worktree_path = self.root / path
            if not worktree_path.is_file():
                continue
            if _git_blob_id(worktree_path.read_bytes(), self.git_object_format) != object_id:
                self.fail(
                    "index_worktree_byte_mismatch",
                    (
                        "Raw worktree bytes differ from the staged Git blob; "
                        "normalize line endings before building manifests."
                    ),
                    path,
                )

    def _verify_required_files_are_tracked(self) -> None:
        for path in self.policy.get("required_tracked", []):
            if not (self.root / path).is_file():
                self.fail("required_file_missing", "A required public-release file is missing.", path)
            elif path not in self.tracked_modes and not self.candidate:
                self.fail("required_file_untracked", "A required public-release file is not tracked.", path)

    def _allowed(self, path: str) -> bool:
        if path in set(self.policy.get("allow_exact", [])):
            return True
        suffix = PurePosixPath(path).suffix.casefold()
        for rule in self.policy.get("allow_trees", []):
            prefix = str(rule["prefix"])
            extensions = {str(value).casefold() for value in rule.get("extensions", [])}
            if path.startswith(prefix) and suffix in extensions:
                return True
        return False

    def _verify_paths_and_contents(self) -> None:
        forbidden_segments = {str(item).casefold() for item in self.policy.get("forbidden_segments", [])}
        forbidden_suffixes = {str(item).casefold() for item in self.policy.get("forbidden_suffixes", [])}
        forbidden_names = {str(item).casefold() for item in self.policy.get("forbidden_names", [])}
        binary_extensions = {str(item).casefold() for item in self.policy.get("binary_extensions", [])}
        max_file_bytes = int(self.policy["max_file_bytes"])

        for path in sorted(self.audited_paths):
            pure = PurePosixPath(path)
            if pure.is_absolute() or ".." in pure.parts or path.startswith("/"):
                self.fail("unsafe_repository_path", "Tracked path is absolute or traverses upward.", path)
                continue
            if not self._allowed(path):
                self.fail("path_not_allowlisted", "Tracked path is not in the public allowlist.", path)
            if any(part.casefold() in forbidden_segments for part in pure.parts):
                self.fail("forbidden_directory", "Tracked path enters a forbidden directory.", path)
            if pure.name.casefold() in forbidden_names or pure.name.casefold().startswith(".env."):
                self.fail("forbidden_filename", "Tracked filename is forbidden.", path)
            if pure.suffix.casefold() in forbidden_suffixes:
                self.fail("forbidden_extension", "Tracked file extension is forbidden.", path)

            mode = self.tracked_modes.get(path)
            if mode in {"120000", "160000"}:
                kind = "symlink" if mode == "120000" else "submodule"
                self.fail("forbidden_git_mode", f"Public releases do not allow a tracked {kind}.", path)
            elif mode is not None and mode not in {"100644", "100755"}:
                self.fail("unexpected_git_mode", f"Unexpected Git mode {mode}.", path)

            full_path = self.root / Path(*pure.parts)
            if not full_path.exists():
                self.fail("tracked_file_missing", "Tracked file is missing from the worktree.", path)
                continue
            if full_path.is_symlink():
                self.fail("worktree_symlink", "Worktree symlinks are forbidden.", path)
                continue
            if not full_path.is_file():
                self.fail("not_regular_file", "Tracked entry is not a regular file.", path)
                continue
            size = full_path.stat().st_size
            self.total_bytes += size
            if size > max_file_bytes:
                self.fail(
                    "file_too_large",
                    f"File is {size} bytes; policy maximum is {max_file_bytes} bytes.",
                    path,
                )
            data = full_path.read_bytes()
            if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
                self.fail("git_lfs_pointer", "Git LFS pointers are forbidden in this source release.", path)
            if pure.suffix.casefold() not in binary_extensions:
                self._scan_text(path, data)

        max_total_bytes = int(self.policy["max_total_bytes"])
        if self.total_bytes > max_total_bytes:
            self.fail(
                "repository_too_large",
                f"Audited files total {self.total_bytes} bytes; policy maximum is {max_total_bytes} bytes.",
            )

    def _scan_text(self, path: str, data: bytes) -> None:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            self.fail("non_utf8_text", "Allowlisted text file is not valid UTF-8.", path)
            return
        if path != "release/public-release-policy.json":
            for spec in self.policy.get("sensitive_path_patterns", []):
                if re.search(str(spec["pattern"]), text, flags=re.IGNORECASE):
                    self.fail("sensitive_path", f"Matched sensitive-path rule {spec['id']}.", path)
        for spec in self.policy.get("secret_patterns", []):
            if re.search(str(spec["pattern"]), text, flags=re.IGNORECASE):
                self.fail("secret_pattern", f"Matched secret rule {spec['id']}.", path)
        if path != "release/public-release-policy.json":
            for spec in self.policy.get("forbidden_text_patterns", []):
                if re.search(str(spec["pattern"]), text, flags=re.IGNORECASE):
                    self.fail("forbidden_text", f"Matched forbidden text rule {spec['id']}.", path)

    def _verify_license_and_notice(self) -> None:
        license_spec = self.policy["license"]
        license_path = self.root / str(license_spec["path"])
        if license_path.is_file():
            raw = license_path.read_bytes().replace(b"\r\n", b"\n")
            digest = hashlib.sha256(raw).hexdigest()
            if digest != license_spec["normalized_sha256"]:
                self.fail(
                    "license_digest_mismatch",
                    "LICENSE is not the approved Apache-2.0 text.",
                    str(license_spec["path"]),
                )
            text = raw.decode("utf-8", errors="replace")
            for phrase in license_spec.get("required_phrases", []):
                if phrase not in text:
                    self.fail(
                        "license_phrase_missing",
                        f"LICENSE is missing required phrase: {phrase}",
                        str(license_spec["path"]),
                    )

        notice_spec = self.policy["notice"]
        notice_path = self.root / str(notice_spec["path"])
        if notice_path.is_file():
            text = notice_path.read_text(encoding="utf-8")
            for phrase in notice_spec.get("required_phrases", []):
                if phrase.casefold() not in text.casefold():
                    self.fail(
                        "notice_phrase_missing",
                        f"NOTICE is missing required phrase: {phrase}",
                        str(notice_spec["path"]),
                    )

        for copy_relative in ("runtime/LICENSE", "skill/editaplot/LICENSE"):
            copy_path = self.root / copy_relative
            if (
                license_path.is_file()
                and copy_path.is_file()
                and copy_path.read_bytes() != license_path.read_bytes()
            ):
                self.fail(
                    "license_copy_mismatch", "Bundled LICENSE copy differs from root LICENSE.", copy_relative
                )
        for copy_relative in ("runtime/NOTICE", "skill/editaplot/NOTICE"):
            copy_path = self.root / copy_relative
            if (
                notice_path.is_file()
                and copy_path.is_file()
                and copy_path.read_bytes() != notice_path.read_bytes()
            ):
                self.fail(
                    "notice_copy_mismatch", "Bundled NOTICE copy differs from root NOTICE.", copy_relative
                )

    @staticmethod
    def _requirement_lines(path: Path) -> list[str]:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    @staticmethod
    def _canonical_package(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).casefold()

    def _parse_exact_requirements(self, relative: str) -> dict[str, str]:
        path = self.root / relative
        if not path.is_file():
            return {}
        result: dict[str, str] = {}
        for line in self._requirement_lines(path):
            match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)", line)
            if match is None:
                self.fail(
                    "dependency_not_exact", "Dependency entry is not an exact name==version pin.", relative
                )
                continue
            name, version = match.groups()
            canonical = self._canonical_package(name)
            if canonical in result:
                self.fail("duplicate_dependency", f"Dependency {name} is listed more than once.", relative)
            result[canonical] = version
        return result

    def _verify_dependency_lock(self) -> None:
        spec = self.policy["dependency_lock"]
        direct_path = str(spec["direct_requirements"])
        runtime_copy = str(spec["runtime_requirements_copy"])
        lock_paths = [str(value) for value in spec["constraint_copies"]]

        direct = self._parse_exact_requirements(direct_path)
        locks = [self._parse_exact_requirements(path) for path in lock_paths]
        if locks and len(locks[0]) < int(spec["minimum_locked_packages"]):
            self.fail(
                "dependency_lock_too_small",
                f"Lock has {len(locks[0])} packages; expected at least {spec['minimum_locked_packages']}.",
                lock_paths[0],
            )
        if locks:
            expected_locked = {
                self._canonical_package(str(name)) for name in spec["expected_locked_packages"]
            }
            if set(locks[0]) != expected_locked:
                missing = sorted(expected_locked - set(locks[0]))
                extra = sorted(set(locks[0]) - expected_locked)
                self.fail(
                    "dependency_lock_exact_set_mismatch",
                    f"Missing={missing}; extra={extra}.",
                    lock_paths[0],
                )
            for name, version in direct.items():
                if locks[0].get(name) != version:
                    self.fail(
                        "direct_lock_mismatch",
                        f"Direct dependency {name} is not identically pinned in the lock.",
                        lock_paths[0],
                    )

        existing_lock_bytes = [
            (self.root / path).read_bytes() for path in lock_paths if (self.root / path).is_file()
        ]
        if len(existing_lock_bytes) == len(lock_paths) and len(set(existing_lock_bytes)) != 1:
            self.fail("constraint_copies_differ", "Dependency constraint copies are not byte-identical.")

        direct_file = self.root / direct_path
        runtime_file = self.root / runtime_copy
        if (
            direct_file.is_file()
            and runtime_file.is_file()
            and direct_file.read_bytes() != runtime_file.read_bytes()
        ):
            self.fail(
                "runtime_requirements_stale",
                "Bundled runtime requirements differ from the release requirements.",
                runtime_copy,
            )

        pyproject_relative = str(spec["runtime_pyproject"])
        pyproject_path = self.root / pyproject_relative
        if pyproject_path.is_file():
            pyproject_text = pyproject_path.read_text(encoding="utf-8")
            match = re.search(
                r"(?ms)^dependencies\s*=\s*\[(.*?)^\]",
                pyproject_text,
            )
            if match is None:
                self.fail(
                    "runtime_pyproject_dependencies_missing",
                    "runtime pyproject has no project dependencies array.",
                    pyproject_relative,
                )
            else:
                declared: dict[str, str] = {}
                for requirement in re.findall(r'"([^"\r\n]+)"', match.group(1)):
                    parsed = re.fullmatch(
                        r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)",
                        requirement,
                    )
                    if parsed is None:
                        self.fail(
                            "runtime_pyproject_dependency_not_exact",
                            f"Dependency is not exactly pinned: {requirement}",
                            pyproject_relative,
                        )
                        continue
                    name, version = parsed.groups()
                    declared[self._canonical_package(name)] = version
                if declared != direct:
                    self.fail(
                        "runtime_pyproject_dependency_mismatch",
                        "runtime project dependencies differ from doctor --repair requirements.",
                        pyproject_relative,
                    )

    def _verify_gallery(self) -> None:
        spec = self.policy["gallery"]
        directory = self.root / str(spec["directory"])
        manifest_path = self.root / str(spec["manifest"])
        if not directory.is_dir() or not manifest_path.is_file():
            self.fail("gallery_missing", "Gallery directory or manifest is missing.", str(spec["directory"]))
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.fail(
                "gallery_manifest_invalid", f"Gallery manifest is invalid: {exc}", str(spec["manifest"])
            )
            return
        cases = manifest.get("cases")
        if not isinstance(cases, list):
            self.fail(
                "gallery_cases_invalid", "Gallery manifest cases must be a list.", str(spec["manifest"])
            )
            return
        expected_count = int(spec["expected_case_count"])
        if manifest.get("case_count") != len(cases) or len(cases) != expected_count:
            self.fail(
                "gallery_count_mismatch",
                f"Gallery must contain exactly {expected_count} manifest cases.",
                str(spec["manifest"]),
            )
        records: dict[str, dict[str, Any]] = {}
        for record in cases:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                self.fail(
                    "gallery_record_invalid", "Gallery record lacks a string id.", str(spec["manifest"])
                )
                continue
            case_id = record["id"]
            if re.fullmatch(r"[a-z0-9][a-z0-9-]*", case_id) is None:
                self.fail("gallery_id_unsafe", "Gallery id is not a safe slug.", str(spec["manifest"]))
            if case_id in records:
                self.fail("gallery_id_duplicate", f"Duplicate gallery id: {case_id}", str(spec["manifest"]))
            records[case_id] = record
        actual = {path.stem: path for path in directory.glob("*.png") if path.is_file()}
        if set(records) != set(actual):
            missing = sorted(set(records) - set(actual))
            extra = sorted(set(actual) - set(records))
            self.fail(
                "gallery_exact_set_mismatch", f"Missing={missing}; extra={extra}.", str(spec["directory"])
            )
        for case_id in sorted(set(records) & set(actual)):
            path = actual[case_id]
            record = records[case_id]
            if path.stat().st_size != record.get("size_bytes"):
                self.fail(
                    "gallery_size_mismatch",
                    "PNG size does not match its manifest.",
                    path.relative_to(self.root).as_posix(),
                )
            if _sha256(path) != record.get("sha256"):
                self.fail(
                    "gallery_hash_mismatch",
                    "PNG hash does not match its manifest.",
                    path.relative_to(self.root).as_posix(),
                )
            if spec.get("reject_nonempty_png_text"):
                for keyword, value in _png_text(path):
                    if value.strip():
                        self.fail(
                            "png_text_metadata",
                            f"PNG contains non-empty text metadata {keyword!r}.",
                            path.relative_to(self.root).as_posix(),
                        )

    def _verify_palettes(self) -> None:
        spec = self.policy["palettes"]
        source = self.root / str(spec["source"])
        copy = self.root / str(spec["skill_copy"])
        if not source.is_dir() or not copy.is_dir():
            self.fail("palette_directory_missing", "Palette source or Skill copy is missing.")
            return
        source_files = _relative_hashes(source)
        copy_files = _relative_hashes(copy)
        if source_files != copy_files:
            missing = sorted(set(source_files) - set(copy_files))
            extra = sorted(set(copy_files) - set(source_files))
            changed = sorted(
                name for name in set(source_files) & set(copy_files) if source_files[name] != copy_files[name]
            )
            self.fail("palette_copies_differ", f"Missing={missing}; extra={extra}; changed={changed}.")
        expected_files = int(spec["expected_file_count"])
        if len(source_files) != expected_files:
            self.fail(
                "palette_file_count",
                f"Palette asset set has {len(source_files)} files; expected {expected_files}.",
                str(spec["source"]),
            )

        catalog_path = self.root / str(spec["catalog"])
        if not catalog_path.is_file():
            self.fail("palette_catalog_missing", "Palette catalog is missing.", str(spec["catalog"]))
            return
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.fail("palette_catalog_invalid", f"Palette catalog is invalid: {exc}", str(spec["catalog"]))
            return
        palettes = catalog.get("palettes")
        if not isinstance(palettes, list):
            self.fail(
                "palette_list_invalid", "Palette catalog must contain a palettes list.", str(spec["catalog"])
            )
            return
        if len(palettes) != int(spec["expected_palette_count"]):
            self.fail(
                "palette_count",
                "Palette catalog count is not the frozen release count.",
                str(spec["catalog"]),
            )
        public_count = sum(item.get("public_default") is True for item in palettes if isinstance(item, dict))
        if public_count != int(spec["expected_public_palette_count"]):
            self.fail(
                "public_palette_count",
                "Public palette count is not the frozen release count.",
                str(spec["catalog"]),
            )
        palette_ids = [item.get("palette_id") for item in palettes if isinstance(item, dict)]
        if len(palette_ids) != len(set(palette_ids)) or any(
            not isinstance(value, str) for value in palette_ids
        ):
            self.fail("palette_ids_invalid", "Palette ids must be unique strings.", str(spec["catalog"]))

    def _verify_runtime_manifest(self) -> None:
        spec = self.policy["runtime_manifest"]
        directory = self.root / str(spec["directory"])
        manifest_path = self.root / str(spec["manifest"])
        if not directory.is_dir() or not manifest_path.is_file():
            self.fail(
                "runtime_manifest_missing",
                "Runtime directory or manifest is missing.",
                str(spec["directory"]),
            )
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.fail(
                "runtime_manifest_invalid", f"Runtime manifest is invalid: {exc}", str(spec["manifest"])
            )
            return
        records = manifest.get("files")
        if not isinstance(records, list):
            self.fail(
                "runtime_records_invalid", "Runtime manifest files must be a list.", str(spec["manifest"])
            )
            return
        by_path: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                self.fail(
                    "runtime_record_invalid",
                    "Runtime manifest record lacks a string path.",
                    str(spec["manifest"]),
                )
                continue
            relative = record["path"].replace("\\", "/")
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts:
                self.fail("runtime_path_unsafe", "Runtime manifest path is unsafe.", relative)
                continue
            if relative in by_path:
                self.fail("runtime_path_duplicate", "Runtime manifest repeats a path.", relative)
            by_path[relative] = record
        if manifest.get("file_count") != len(records):
            self.fail(
                "runtime_count_mismatch", "Runtime manifest file_count is stale.", str(spec["manifest"])
            )
        runtime_prefix = f"{str(spec['directory']).rstrip('/')}/"
        manifest_relative = str(spec["manifest"])
        actual = {
            tracked[len(runtime_prefix) :]: self.root / tracked
            for tracked in self.audited_paths
            if tracked.startswith(runtime_prefix) and tracked != manifest_relative
        }
        if set(by_path) != set(actual):
            missing = sorted(set(by_path) - set(actual))
            extra = sorted(set(actual) - set(by_path))
            self.fail(
                "runtime_exact_set_mismatch", f"Missing={missing}; extra={extra}.", str(spec["manifest"])
            )
        for relative in sorted(set(by_path) & set(actual)):
            path = actual[relative]
            record = by_path[relative]
            if path.stat().st_size != record.get("size_bytes"):
                self.fail(
                    "runtime_size_mismatch",
                    "Runtime file size does not match its manifest.",
                    f"runtime/{relative}",
                )
            if _sha256(path) != record.get("sha256"):
                self.fail(
                    "runtime_hash_mismatch",
                    "Runtime file hash does not match its manifest.",
                    f"runtime/{relative}",
                )

    def _verify_asset_provenance(self) -> None:
        spec = self.policy["asset_provenance"]
        manifest_relative = str(spec["manifest"])
        manifest_path = self.root / manifest_relative
        documentation = self.root / str(spec["documentation"])
        if not manifest_path.is_file() or not documentation.is_file():
            self.fail(
                "asset_provenance_missing",
                "Asset provenance manifest or documentation is missing.",
                manifest_relative,
            )
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.fail(
                "asset_provenance_invalid",
                f"Asset provenance manifest is invalid: {exc}",
                manifest_relative,
            )
            return
        for field, policy_key in (
            ("inventory_generator", "inventory_generator"),
            ("gallery_fixture_generator", "gallery_fixture_generator"),
        ):
            binding = manifest.get(field)
            expected_path = str(spec[policy_key])
            expected_file = self.root / expected_path
            if (
                not isinstance(binding, dict)
                or binding.get("path") != expected_path
                or not expected_file.is_file()
                or binding.get("sha256") != _sha256(expected_file)
            ):
                self.fail(
                    "asset_provenance_generator_mismatch",
                    f"Generator binding is missing or stale: {expected_path}",
                    manifest_relative,
                )
        review = manifest.get("human_review")
        if (
            not isinstance(review, dict)
            or review.get("decision") != spec["required_review_decision"]
            or not isinstance(review.get("reviewed_on"), str)
            or not review["reviewed_on"].strip()
            or not isinstance(review.get("scope"), str)
            or not review["scope"].strip()
        ):
            self.fail(
                "asset_provenance_review_missing",
                "Asset provenance lacks the required human review record.",
                manifest_relative,
            )
        records = manifest.get("assets")
        if not isinstance(records, list):
            self.fail(
                "asset_provenance_records_invalid",
                "Asset provenance assets must be a list.",
                manifest_relative,
            )
            return

        by_path: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                self.fail(
                    "asset_provenance_record_invalid",
                    "Asset provenance record lacks a string path.",
                    manifest_relative,
                )
                continue
            relative = record["path"].replace("\\", "/")
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or pure.suffix.casefold() not in {".csv", ".png"}:
                self.fail("asset_provenance_path_unsafe", "Asset path is unsafe or unsupported.", relative)
                continue
            if relative in by_path:
                self.fail("asset_provenance_duplicate", "Asset path is repeated.", relative)
            by_path[relative] = record

        expected_count = int(spec["expected_asset_count"])
        if manifest.get("asset_count") != len(records) or len(records) != expected_count:
            self.fail(
                "asset_provenance_count_mismatch",
                f"Asset provenance must contain exactly {expected_count} records.",
                manifest_relative,
            )
        actual = {
            relative: self.root / relative
            for relative in self.audited_paths
            if PurePosixPath(relative).suffix.casefold() in {".csv", ".png"}
        }
        if set(by_path) != set(actual):
            missing = sorted(set(actual) - set(by_path))
            extra = sorted(set(by_path) - set(actual))
            self.fail(
                "asset_provenance_exact_set_mismatch",
                f"Missing={missing}; extra={extra}.",
                manifest_relative,
            )
        for relative in sorted(set(by_path) & set(actual)):
            path = actual[relative]
            record = by_path[relative]
            if record.get("size_bytes") != path.stat().st_size:
                self.fail("asset_provenance_size_mismatch", "Asset size is stale.", relative)
            if record.get("sha256") != _sha256(path):
                self.fail("asset_provenance_hash_mismatch", "Asset hash is stale.", relative)
            if not isinstance(record.get("kind"), str) or not record["kind"].strip():
                self.fail("asset_provenance_kind_missing", "Asset classification is missing.", relative)
            else:
                expected_kind = _expected_asset_kind(relative)
                if expected_kind is None or record["kind"] != expected_kind:
                    self.fail(
                        "asset_provenance_kind_mismatch",
                        f"Asset classification must be {expected_kind!r}.",
                        relative,
                    )
            if (
                spec.get("require_synthetic_or_generated")
                and record.get("synthetic_or_generated") is not True
            ):
                self.fail(
                    "asset_not_synthetic_or_generated",
                    "Public asset is not explicitly synthetic or generated.",
                    relative,
                )
            if spec.get("require_contains_phi_false") and record.get("contains_phi") is not False:
                self.fail("asset_phi_status", "Public asset is not explicitly marked PHI-free.", relative)
            if path.suffix.casefold() == ".png":
                png_text = record.get("png_text")
                actual_text = dict(_png_text(path))
                if not isinstance(png_text, dict) or png_text != actual_text:
                    self.fail(
                        "asset_png_metadata_mismatch",
                        "PNG text metadata differs from its provenance record.",
                        relative,
                    )
                if "__exif__" in actual_text:
                    self.fail("asset_png_exif", "Public PNG contains an EXIF chunk.", relative)
                if "__invalid_png__" in actual_text:
                    self.fail("asset_png_invalid", actual_text["__invalid_png__"], relative)
                for keyword, value in actual_text.items():
                    if not keyword.startswith("__"):
                        self._scan_text(
                            f"{relative}#png-metadata:{keyword}",
                            value.encode("utf-8", errors="replace"),
                        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_blob_id(data: bytes, object_format: str = "sha1") -> str:
    digest = hashlib.new(object_format)
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def _relative_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): _sha256(path)
        for path in directory.rglob("*")
        if path.is_file()
    }


def _expected_asset_kind(relative: str) -> str | None:
    if relative.startswith("assets/gallery/"):
        return "verified_origin_export_from_synthetic_fixture"
    if relative.startswith("assets/palettes/") or relative.startswith("skill/editaplot/assets/palettes/"):
        return "generated_original_palette_asset"
    if relative == "runtime/src/origin_sciplot/resources/app_icon.png":
        return "original_application_icon"
    if relative == "runtime/templates/xps_c1s_fit/preview.png":
        return "generated_synthetic_ui_preview"
    if relative.startswith("examples/"):
        return "synthetic_public_example"
    if relative.startswith("runtime/templates/"):
        return "synthetic_runtime_fixture"
    return None


def _png_chunks(path: Path) -> Iterable[tuple[bytes, bytes]]:
    with path.open("rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG file")
        chunk_index = 0
        seen_ihdr = False
        seen_idat = False
        while True:
            raw_length = handle.read(4)
            if not raw_length:
                raise ValueError("PNG is missing IEND")
            if len(raw_length) != 4:
                raise ValueError("truncated PNG chunk length")
            length = struct.unpack(">I", raw_length)[0]
            kind = handle.read(4)
            payload = handle.read(length)
            checksum = handle.read(4)
            if len(kind) != 4 or len(payload) != length or len(checksum) != 4:
                raise ValueError("truncated PNG chunk")
            expected_crc = struct.unpack(">I", checksum)[0]
            if zlib.crc32(kind + payload) & 0xFFFFFFFF != expected_crc:
                raise ValueError("PNG chunk CRC mismatch")
            if kind == b"IHDR":
                if chunk_index != 0 or seen_ihdr or len(payload) != 13:
                    raise ValueError("PNG has an invalid IHDR")
                seen_ihdr = True
            elif chunk_index == 0:
                raise ValueError("PNG IHDR is not the first chunk")
            if kind == b"IDAT":
                seen_idat = True
            if kind == b"IEND" and (payload or not seen_ihdr or not seen_idat):
                raise ValueError("PNG has an invalid IEND or no IDAT")
            yield kind, payload
            chunk_index += 1
            if kind == b"IEND":
                if handle.read(1):
                    raise ValueError("PNG contains trailing data after IEND")
                return


def _decompress_png_text(payload: bytes) -> bytes:
    decompressor = zlib.decompressobj()
    output = bytearray()
    pending = payload
    while pending:
        allowance = MAX_PNG_TEXT_BYTES + 1 - len(output)
        if allowance <= 0:
            raise ValueError("PNG text metadata exceeds the release limit")
        output.extend(decompressor.decompress(pending, allowance))
        pending = decompressor.unconsumed_tail
        if pending and len(output) > MAX_PNG_TEXT_BYTES:
            raise ValueError("PNG text metadata exceeds the release limit")
        if not pending:
            break
    allowance = MAX_PNG_TEXT_BYTES + 1 - len(output)
    output.extend(decompressor.flush(max(1, allowance)))
    if len(output) > MAX_PNG_TEXT_BYTES or not decompressor.eof:
        raise ValueError("PNG text metadata is oversized or truncated")
    return bytes(output)


PUBLIC_PNG_CHUNKS = frozenset({b"IHDR", b"IDAT", b"IEND", b"pHYs", b"tEXt", b"tIME"})


def _png_text(path: Path) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    seen_keywords: set[str] = set()
    try:
        for kind, payload in _png_chunks(path):
            if kind not in PUBLIC_PNG_CHUNKS:
                label = kind.decode("ascii", errors="backslashreplace")
                raise ValueError(f"PNG chunk {label!r} is not allowed in public assets")
            if kind == b"tEXt":
                keyword, separator, text = payload.partition(b"\0")
                if not separator:
                    raise ValueError("PNG contains a malformed tEXt chunk without a separator")
                if not 1 <= len(keyword) <= 79:
                    raise ValueError("PNG tEXt keyword length is outside 1..79 bytes")
                decoded_keyword = keyword.decode("latin-1", errors="replace")
                if decoded_keyword.startswith("__"):
                    raise ValueError("PNG tEXt keyword uses a reserved release-audit prefix")
                if decoded_keyword in seen_keywords:
                    raise ValueError(f"PNG contains duplicate text keyword {decoded_keyword!r}")
                seen_keywords.add(decoded_keyword)
                values.append((decoded_keyword, text.decode("latin-1", errors="replace")))
    except (OSError, ValueError, zlib.error) as exc:
        values.append(("__invalid_png__", str(exc)))
    return values


def _load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read release policy {path}: {exc}") from exc
    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise RuntimeError("Unsupported public-release policy schema.")
    return policy


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_human(report: dict[str, Any]) -> None:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"{status}: {report['policy']} ({report['mode']} mode)")
    print(
        f"Tracked {report['tracked_file_count']} files; audited {report['audited_file_count']} "
        f"files / {report['audited_total_bytes']} bytes."
    )
    for error in report["errors"]:
        location = f" [{error['path']}]" if "path" in error else ""
        print(f"- {error['code']}{location}: {error['message']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_default_root(), help="Repository root")
    parser.add_argument(
        "--policy",
        type=Path,
        default=None,
        help="Policy JSON (default: <root>/release/public-release-policy.json)",
    )
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="Pre-stage review: include only missing files listed in required_tracked",
    )
    parser.add_argument("--json", action="store_true", help="Emit the audit report as JSON")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    policy_path = (
        args.policy.resolve() if args.policy is not None else root / "release" / "public-release-policy.json"
    )
    try:
        policy = _load_policy(policy_path)
        report = ReleaseAudit(root, policy, candidate=args.candidate).run()
    except RuntimeError as exc:
        if args.json:
            print(json.dumps({"ok": False, "fatal_error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
