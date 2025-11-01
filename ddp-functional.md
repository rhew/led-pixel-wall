# DDP Streaming Functional Plan

This document captures the initial scope for Distributed Display Protocol (DDP) streaming on the LED Pixel Wall controller.

## References
- 3waylabs – “Distributed Display Protocol Specification v1.0” (http://www.3waylabs.com/ddp/).
- WLED knowledge base – “Realtime Control via DDP” (https://kno.wled.ge/interfaces/ddp/).

## Specification Notes (from 3waylabs)
- DDP packets begin with a 10-byte header: `Flags+Version`, `Sequence`, `Data Type`, `Offset` (uint16), `Data Length` (uint16), and `Data ID` (uint16).
- The upper nibble of the first byte encodes flag bits (e.g., `0x40` for data push, `0x20` for queries, `0x10` for time sync). The lower nibble carries the protocol version (`0x1` at the time of writing).
- Supported data types include `0x01` (packed RGB, 24-bit) and `0x02` (packed RGBW, 32-bit); values `0x03–0x7F` remain reserved. Receivers must drop unsupported types.
- `Offset` denotes the starting channel index within the receiver’s logical pixel buffer; consecutive packets may target different regions of the same frame.
- `Data Length` is the byte count for the payload that follows the header; packets exceeding the negotiated capacity are to be dropped.
- `Data ID` allows segmenting multiple logical frame buffers; default to `0` while we implement a single canvas.
- Sequence numbers roll over at 255; receivers choose how to treat out-of-order or duplicate frames (see MVP sequence handling below).

## Target Feature Set (MVP)
- **Transport**: UDP listener bound to host `0.0.0.0` port `4048` (configurable).
- **Packet handling**: Accept DDP v1 pixel data frames that set the data flag (`0x40`) and advertise version `0x1`; expect `Data Type = 0x01` (packed RGB) and log/drop any unsupported types.
- **Unsupported bits**: If additional flag bits are asserted (query, time sync, reserved), log a warning and discard the payload so misconfigured senders are visible without corrupting state.
- **Sequence enforcement**: Track the sequence byte, discard out-of-order frames, and emit periodic stats so operators can spot packet loss.
- **Header support**: Parse sequence byte, 16-bit data offset, and 16-bit data length; ignore data ID / reserved fields for now.
- **Frame application**: Copy payload directly into the sequential LED buffer up to the provisioned LED count; log and drop packets that target pixels outside the configured range.
- **Buffer management**: Size working buffers from the configured LED count (max payload `count × 3` bytes) once provisioning completes, and validate offsets/lengths per packet before writing to avoid overruns even when upstream layout metadata is stale.
- **Status reporting**: Emit a single info log when a stream resumes after idle, and one when it times out, to aid operators without flooding logs.
- **Drop stats**: Log sequence-drop counts every 5 seconds while packets flow so operators can monitor link health.
- **Runtime mode**: Always operate as a DDP receiver; local effects are out of scope for this iteration.

## Configuration & Persistence
- Surface DDP listen port (default 4048) in the existing HTTP provisioning portal so installers can match upstream tooling without reflashing.
- Persist LED geometry (count, layout) once during provisioning so we can size buffers safely; no toggle to disable streaming.

## Out-of-Scope (Future Considerations)
- RGBW payloads (`Data Type = 0x02`), HDR scaling, or per-pixel metadata.
- Compression, timecode, or bidirectional acknowledgements.
- Multicast, VLAN tagging, or encrypted tunnels.
- Multi-segment data IDs and distributed render clustering.
