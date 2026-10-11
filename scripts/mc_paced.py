"""Paced MCP access: the mod allows 60 requests/minute shared by all local clients."""
import json
import time
from pathlib import Path

from mcp import Client

ROOT = Path(__file__).resolve().parent.parent
_CFG = json.loads((ROOT / 'config/world.json').read_text())

D = 'minecraft:overworld'
UUID = _CFG.get('player_uuid', 'f89f7477-c4ee-4997-a8ee-be75b4d8b75a')


class Paced:
    """Rate-limited MCP world client."""

    def __init__(self, port=8765, interval=1.1):
        """
        @param port: world (8765) or view (8766) MCP port
        @param interval: minimum seconds between calls
        """
        self.client = Client(port, resume_stateless=True)
        self.interval = interval
        self.last = 0.0

    def call(self, name, args):
        """Call an MCP tool and return the raw result dict.

        @param name: tool name
        @param args: tool arguments
        @returns: MCP tools/call result
        """
        time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
        try:
            return self.client.call(name, args)
        finally:
            self.last = time.monotonic()

    def text(self, name, args):
        """Call an MCP tool and join text content blocks.

        @param name: tool name
        @param args: tool arguments
        @returns: concatenated text
        """
        r = self.call(name, args)
        return '\n'.join(x['text'] for x in r['content'] if x['type'] == 'text')


def xyz(p):
    """Convert [x,y,z] to an MCP position dict.

    @param p: sequence of three numbers
    @returns: {'x','y','z'} dict
    """
    return dict(zip('xyz', p))


def box(lo, hi):
    """Build an MCP axis-aligned box from two corners.

    @param lo: low corner [x,y,z]
    @param hi: high corner [x,y,z]
    @returns: {'from','to'} dict
    """
    return {'from': xyz(lo), 'to': xyz(hi)}
