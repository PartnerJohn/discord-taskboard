import asyncio
import json
import logging
from dataclasses import dataclass, field

import websockets

logger = logging.getLogger(__name__)


@dataclass
class VTubeStudioController:
    """Controls a Live2D model via VTube Studio's WebSocket API."""
    host: str = "localhost"
    port: int = 8001
    plugin_name: str = "VTuber AI Agent"
    plugin_developer: str = "Discord Taskboard"
    _ws: object = field(default=None, repr=False)
    _auth_token: str = ""
    _request_id: int = 0

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def connect(self):
        try:
            self._ws = await websockets.connect(self.uri)
            logger.info("Connected to VTube Studio at %s", self.uri)
            await self._authenticate()
        except Exception as e:
            logger.error("Failed to connect to VTube Studio: %s", e)
            self._ws = None
            raise

    async def disconnect(self):
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _send(self, msg_type: str, data: dict = None) -> dict:
        if not self._ws:
            raise ConnectionError("Not connected to VTube Studio")
        self._request_id += 1
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": str(self._request_id),
            "messageType": msg_type,
            "data": data or {},
        }
        await self._ws.send(json.dumps(payload))
        resp = await self._ws.recv()
        return json.loads(resp)

    async def _authenticate(self):
        if self._auth_token:
            resp = await self._send("AuthenticationRequest", {
                "pluginName": self.plugin_name,
                "pluginDeveloper": self.plugin_developer,
                "authenticationToken": self._auth_token,
            })
            if resp.get("data", {}).get("authenticated"):
                logger.info("Authenticated with VTube Studio")
                return

        resp = await self._send("AuthenticationTokenRequest", {
            "pluginName": self.plugin_name,
            "pluginDeveloper": self.plugin_developer,
        })
        self._auth_token = resp.get("data", {}).get("authenticationToken", "")

        if self._auth_token:
            resp = await self._send("AuthenticationRequest", {
                "pluginName": self.plugin_name,
                "pluginDeveloper": self.plugin_developer,
                "authenticationToken": self._auth_token,
            })
            if resp.get("data", {}).get("authenticated"):
                logger.info("Authenticated with VTube Studio")
            else:
                logger.warning("Authentication failed — approve the plugin in VTube Studio")

    async def set_expression(self, expression_file: str):
        """Activate a Live2D expression (e.g., 'happy.exp3.json')."""
        await self._send("ExpressionActivationRequest", {
            "expressionFile": expression_file,
            "active": True,
        })

    async def clear_expression(self, expression_file: str):
        await self._send("ExpressionActivationRequest", {
            "expressionFile": expression_file,
            "active": False,
        })

    async def trigger_hotkey(self, hotkey_id: str):
        """Trigger a VTube Studio hotkey by ID."""
        await self._send("HotkeyTriggerRequest", {
            "hotkeyID": hotkey_id,
        })

    async def set_parameter(self, param_name: str, value: float, weight: float = 1.0):
        """Set a Live2D parameter value (e.g., mouth open, eye blink)."""
        await self._send("InjectParameterDataRequest", {
            "parameterValues": [{
                "id": param_name,
                "value": value,
                "weight": weight,
            }],
        })

    async def animate_talking(self, duration: float = 0.1, mouth_open: float = 0.8):
        """Simulate talking by toggling mouth open/close."""
        await self.set_parameter("MouthOpen", mouth_open)
        await asyncio.sleep(duration)
        await self.set_parameter("MouthOpen", 0.0)

    async def get_available_models(self) -> list[dict]:
        resp = await self._send("AvailableModelsRequest")
        return resp.get("data", {}).get("availableModels", [])

    async def load_model(self, model_id: str):
        await self._send("ModelLoadRequest", {"modelID": model_id})

    async def get_hotkeys(self) -> list[dict]:
        resp = await self._send("HotkeysInCurrentModelRequest")
        return resp.get("data", {}).get("availableHotkeys", [])

    async def get_expressions(self) -> list[dict]:
        resp = await self._send("ExpressionStateRequest")
        return resp.get("data", {}).get("expressions", [])
