# Source Manifest Tool

소스코드 파일의 메타데이터 표(파일명/버전/수정일자/수정일시/체크섬/라인수/파일크기/설명)를 자동으로 생성·갱신하는 간단한 유틸리티입니다. 체크섬은 ZIP 도구에서 자주 쓰는 CRC32를 사용하며 `0x12345678` 형식으로 기록됩니다.
수정일자/수정일시는 UTC가 아닌 **실행 환경의 로컬 타임** 기준으로 기록됩니다.

## 핵심 아이디어

- 초기 실행 시 `SOURCE_MANIFEST.md`를 생성합니다.
- 이후 실행 시 기존 표와 비교해 **체크섬이 바뀐 파일만 버전이 0.1씩 증가**합니다.
  - 신규 파일: `1.0`
  - 변경 파일: `1.0 -> 1.1 -> 1.2`
  - 미변경 파일: 버전 유지
- 설명(`description`) 컬럼은 기존 값이 비어있지 않다면 그대로 유지되어 문서화 내용이 사라지지 않습니다.

## 사용법

```bash
python3 source_manifest_tool.py --root . --manifest SOURCE_MANIFEST.md
```

드라이런(파일 저장 없이 출력만):

```bash
python3 source_manifest_tool.py --dry-run
```

### 자주 쓰는 옵션

- `--include` : 스캔 포함 패턴 추가 (여러 번 사용 가능)
- `--exclude` : 제외 패턴 추가 (여러 번 사용 가능)
- `--sync-mtime-from-manifest` : 체크섬은 동일하지만 수정일시가 다른 파일의 mtime을 manifest 값으로 동기화 (기본 OFF)
- `--check` : `md5sum -c checksumfile` 처럼 manifest의 `checksum_crc32` 기준으로 파일 무결성 검증

예시:

```bash
python3 source_manifest_tool.py \
  --include '*.py' \
  --include '*.md' \
  --exclude 'docs/generated/*'
```

수정일시 불일치 동기화:

```bash
python3 source_manifest_tool.py --sync-mtime-from-manifest
```

기본값(OFF)에서는 파일 mtime을 변경하지 않고 불일치 파일 목록만 출력합니다.

체크섬 검증(`md5sum -c` 유사):

```bash
python3 source_manifest_tool.py --check
```

## 생성되는 표 예시

| filename | version | modified_date | modified_datetime | checksum_crc32 | line_count | file_size_bytes | description |
|---|---|---|---|---|---|---|---|
| source_manifest_tool.py | 1.2 | 2026.04.17 | 2026.04.17 14:23:59 | ... | 210 | 7024 | 메인 유틸리티 |

## 운영 팁

- CI에서 실행해 manifest를 자동 업데이트하면 변경 추적이 편합니다.
- release 시점에만 실행하도록 해도 문서화 품질을 높일 수 있습니다.
- 필요 시 major/minor/patch 형태로 확장할 수 있습니다.
