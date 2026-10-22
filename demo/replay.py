import argparse
import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from agent.llm.scripted import ScriptedProvider
from agent.memory.lossy import LossySummarizer
from agent.memory.summarize import summarize
from agent.repo import users
from agent.settings import AgentSettings
from agent.ui.view import claim_rows, verified_rows
from demo.harness import Harness, build_harness

TIMELINE = Path(__file__).parent / "timeline.yaml"


@dataclass
class StepResult:
    index: int
    narrate: str
    said: str | None = None
    reply: str | None = None
    result: dict | None = None
    notes: list[str] = field(default_factory=list)


def load_timeline(path: Path = TIMELINE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def scripted(timeline: dict) -> ScriptedProvider:
    provider = ScriptedProvider()
    for step in timeline["steps"]:
        if "say" in step:
            provider.add(step["say"], {"extract": step.get("extract", {}), "steps": step.get("steps", [])})
    return provider


def live_provider():
    from agent.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(os.environ["ANTHROPIC_API_KEY"], os.environ.get("ANTHROPIC_MODEL", AgentSettings.anthropic_model))


class Replay:
    def __init__(self, harness: Harness, timeline: dict):
        self.harness = harness
        self.timeline = timeline
        self.user_id = timeline["user"]
        self.position = 0

    @property
    def done(self) -> bool:
        return self.position >= len(self.timeline["steps"])

    @property
    def user(self) -> dict:
        return users.get_user(self.harness.agent_ctx.conn, self.user_id)

    async def next(self) -> StepResult:
        step = self.timeline["steps"][self.position]
        outcome = StepResult(self.position + 1, step.get("narrate", ""))
        self.position += 1
        if "admin" in step:
            slot = step["admin"]["cancel_slot"]
            response = await self.harness.admin(f"slots/{slot}/cancel")
            outcome.notes.append(f"clinic cancelled {slot}; webhooks delivered: {len(response['delivered'])}")
        if "clock" in step:
            self.harness.advance(**step["clock"])
            outcome.notes.append(f"clock advanced {step['clock']} → {self.harness.clock.now().isoformat()}")
        if step.get("new_session"):
            await self.harness.new_session(self.user_id)
            outcome.notes.append("new session started")
        if "say" in step:
            outcome.said = step["say"]
            outcome.result = await self.harness.say(step["say"], self.user_id)
            outcome.reply = outcome.result["reply"]
        if "summary" in step:
            spec = step["summary"]
            llm = LossySummarizer() if spec.get("lossy") else None
            summary = await summarize(self.harness.agent_ctx, self.user_id, date.fromisoformat(spec["day"]), llm=llm)
            verdict = "KEPT" if summary.validated else "REJECTED"
            outcome.notes.append(f"summary {verdict}: {summary.prose}")
            outcome.notes.extend(f"error: {error}" for error in summary.errors)
        return outcome


async def build_replay(directory: Path, live: bool = False, timeline: dict | None = None) -> Replay:
    timeline = timeline or load_timeline()
    llm = live_provider() if live else scripted(timeline)
    harness = await build_harness(directory, llm=llm)
    await harness.login(timeline["user"])
    return Replay(harness, timeline)


def print_panels(replay: Replay) -> None:
    ctx, user = replay.harness.agent_ctx, replay.user
    print("  VERIFIED:")
    for row in verified_rows(ctx, user) or [{"ref": "-", "status": "none", "when": "", "source": "", "observed_ago": ""}]:
        print(f"    {row['ref']:8} {row['status']:10} {row['when']}  (via {row['source']}, {row['observed_ago']})")
    print("  CLAIMED:")
    for claim in reversed(claim_rows(ctx, user)):
        print(f"    {claim['label']:28} {claim['status']:11} said: {claim['raw_text']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay 'the appointment that changed four times'")
    parser.add_argument("--live", action="store_true", help="use the real LLM instead of the scripted one")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        replay = await build_replay(Path(directory), live=args.live)
        print(f"\n=== {replay.timeline['title']} ===")
        while not replay.done:
            step = await replay.next()
            print(f"\n--- Step {step.index}: {step.narrate}")
            for note in step.notes:
                print(f"  * {note}")
            if step.said:
                print(f"  CUSTOMER: {step.said}")
                for line in step.reply.split("\n\n"):
                    print(f"  AGENT:    {line}")
            print_panels(replay)
        await replay.harness.close()


if __name__ == "__main__":
    asyncio.run(main())
