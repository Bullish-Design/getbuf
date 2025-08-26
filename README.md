# getbuf
Get (Protocol) Buf(fers). Takes proto files and generates a UV based Pydantic + FastAPI client/server/models library. Will eventually provide hooks before/after various steps in the generation workflow for further customization/verification.  

# GetBuf

*A Python library and CLI for running Buf against local modules to generate BetterProto v2 async stubs.*

**Status:** In Development

## Installation

```bash
uv tool install getbuf
```

## Usage

```bash
getbuf gen ./examples/memos --buf-gen ./examples/buf.gen.yaml --clean --json
```

For more information, see the full documentation (coming soon).

## Requirements

- Python 3.12+
- `buf` on PATH
- `protoc-gen-python_betterproto` (BetterProto v2) on PATH

## License

MIT