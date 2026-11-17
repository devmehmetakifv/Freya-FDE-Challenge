"""Voice bot: Pipecat pipeline (ElevenLabs STT -> Claude -> ElevenLabs TTS) over WebRTC.

Run: uv run python -m bot.bot   (serves http://localhost:7860, prebuilt test client at /client)
The /start request body may carry {"customer_id": N} to choose who is being "called".
"""

import os

import httpx
from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    EndWorkerFrame,
    FunctionCallResultProperties,
    LLMRunFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from agent.prompt import KICKOFF_MESSAGE, SILENCE_MESSAGE, build_system_prompt
from agent.tools import TOOL_SPECS, CallSession

load_dotenv(override=True)

# The prebuilt /client page sends no body, so it calls customer 1 (Ayşe Kaya) by default.
DEFAULT_CUSTOMER_ID = 1
SILENCE_TIMEOUT_SECS = 8.0

transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


# Wrap the shared CallSession executor as Pipecat tools. end_call resolves without another
# LLM turn (the goodbye was already spoken) and then ends the worker once queued audio is out.
def build_tools(session: CallSession) -> list[FunctionSchema]:
    async def handle(params: FunctionCallParams) -> None:
        result = await session.execute(params.function_name, dict(params.arguments))
        logger.info(f"tool {params.function_name}({dict(params.arguments)}) -> {result}")
        if params.function_name == "end_call":
            await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=False))
            await params.llm.push_frame(EndWorkerFrame(), FrameDirection.DOWNSTREAM)
        else:
            await params.result_callback(result)

    return [
        FunctionSchema(
            name=spec["name"],
            description=spec["description"],
            properties=spec["properties"],
            required=spec["required"],
            handler=handle,
        )
        for spec in TOOL_SPECS
    ]


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    customer_id = int((runner_args.body or {}).get("customer_id", DEFAULT_CUSTOMER_ID))
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    async with httpx.AsyncClient(base_url=os.environ["SLOT_SERVICE_URL"], timeout=10) as http:
        # Open the call on the bank's system first: it tells us who we're talking to.
        session = await CallSession.open(http, customer_id)
        logger.info(f"call {session.call_id} opened for customer {customer_id}")

        # Turkish in, Turkish out. Claude model comes from env so Haiku vs Opus is a one-line swap.
        stt = ElevenLabsRealtimeSTTService(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            settings=ElevenLabsRealtimeSTTService.Settings(language=Language.TR),
        )
        llm = AnthropicLLMService(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            settings=AnthropicLLMService.Settings(
                model=os.environ["AGENT_BRAIN_MODEL"],
                system_instruction=build_system_prompt(session.customer, session.previous_calls),
            ),
        )
        tts = ElevenLabsTTSService(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            settings=ElevenLabsTTSService.Settings(
                voice=os.environ["ELEVENLABS_VOICE_ID"],
                model="eleven_flash_v2_5",
                language=Language.TR,
            ),
        )

        context = LLMContext(tools=build_tools(session))
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                vad_analyzer=SileroVADAnalyzer(), user_idle_timeout=SILENCE_TIMEOUT_SECS
            ),
        )

        # Silence produces no transcript, so the LLM would never get a turn. The idle timer
        # tells it the customer is quiet; the prompt decides: ask once, then record no_response.
        @user_aggregator.event_handler("on_user_turn_idle")
        async def on_user_turn_idle(aggregator):
            if session.ended:
                return
            context.add_message({"role": "user", "content": SILENCE_MESSAGE})
            await worker.queue_frames([LLMRunFrame()])
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                user_aggregator,
                llm,
                tts,
                transport.output(),
                assistant_aggregator,
            ]
        )
        worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True))

        # Outbound call: as soon as the customer "picks up", they say "Alo?" and the agent opens.
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            context.add_message({"role": "user", "content": KICKOFF_MESSAGE})
            await worker.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            await runner.cancel()

        await runner.add_workers(worker)
        await runner.run()


async def bot(runner_args: RunnerArguments) -> None:
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
