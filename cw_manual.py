#!/usr/bin/env python3
"""Manual CW carrier helper for bench TX-power measurement.

Keys a steady unmodulated carrier at one TX power level so you can read a
stable peak on a spectrum analyzer, then de-keys and exits.

Examples:
    # BLE, set -9 dBm, hold carrier 30 s
    python cw_manual.py --ble --power -9 --secs 30

    # TCP node, set -8 dBm, hold 20 s
    python cw_manual.py --tcp 192.168.1.50:5000 --power -8 --secs 20

    # USB serial
    python cw_manual.py --serial /dev/ttyACM0 --power 22 --secs 15

The firmware also auto-stops the carrier after --secs as a safety, so the PA
is never left keyed if this script is interrupted.
"""
import argparse
import asyncio
from meshcore import MeshCore, EventType

CMD_SET_CW = 0x88
CMD_SET_TX_OPTIMIZE = 0x89


async def connect(args):
    if args.tcp:
        host, _, port = args.tcp.partition(":")
        return await MeshCore.create_tcp(host, int(port or 5000))
    if args.serial:
        return await MeshCore.create_serial(args.serial)
    return await MeshCore.create_ble(address=args.ble if args.ble is not True else None)


async def main():
    ap = argparse.ArgumentParser(description="Manual CW carrier for bench measurement")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ble", nargs="?", const=True, help="connect via BLE (optional address)")
    g.add_argument("--tcp", help="connect via TCP host:port")
    g.add_argument("--serial", help="connect via serial port")
    ap.add_argument("--power", type=int, required=True, help="TX power in dBm (e.g. -9..22)")
    ap.add_argument("--secs", type=int, default=30, help="carrier hold time (FW also caps this)")
    args = ap.parse_args()

    mc = await connect(args)
    if mc is None:
        print("Could not connect to node.")
        return
    try:
        # Hold prefs in RAM so the tx-power change doesn't thrash flash.
        await mc.commands.send(b"\x87\x00", [EventType.OK, EventType.ERROR])

        res = await mc.commands.send(
            b"\x0c" + int(args.power).to_bytes(4, "little", signed=True),
            [EventType.OK, EventType.ERROR])
        if res.type == EventType.ERROR:
            print(f"Failed to set TX power: {res.payload}")
            return
        print(f"TX power set to {args.power} dBm")

        secs = args.secs
        start = bytes([CMD_SET_CW, 1, secs & 0xFF, (secs >> 8) & 0xFF])
        res = await mc.commands.send(start, [EventType.OK, EventType.ERROR])
        if res.type == EventType.ERROR:
            print(f"CW start rejected: {res.payload}")
            return
        print(f"CW carrier ON for up to {secs}s — read the peak on the tinySA now.")
        try:
            await asyncio.sleep(secs)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nInterrupted — stopping carrier.")
    finally:
        await mc.commands.send(bytes([CMD_SET_CW, 0]), [EventType.OK, EventType.ERROR])
        await mc.commands.send(b"\x87\x02", [EventType.OK, EventType.ERROR])  # restore prefs
        await mc.disconnect()
        print("CW carrier OFF, prefs restored, disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
