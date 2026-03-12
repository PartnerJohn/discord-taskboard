import logging
from dataclasses import dataclass, field

import obsws_python as obs

logger = logging.getLogger(__name__)


@dataclass
class OBSController:
    """Controls OBS Studio via obs-websocket for streaming management."""
    host: str = "localhost"
    port: int = 4455
    password: str = ""
    _client: obs.ReqClient | None = field(default=None, repr=False)

    def connect(self):
        try:
            self._client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password or None,
            )
            version = self._client.get_version()
            logger.info("Connected to OBS %s (WebSocket %s)",
                        version.obs_version, version.obs_web_socket_version)
        except Exception as e:
            logger.error("Failed to connect to OBS: %s", e)
            self._client = None
            raise

    def disconnect(self):
        if self._client:
            self._client = None

    def start_streaming(self):
        if not self._client:
            raise ConnectionError("Not connected to OBS")
        self._client.start_stream()
        logger.info("Streaming started")

    def stop_streaming(self):
        if not self._client:
            raise ConnectionError("Not connected to OBS")
        self._client.stop_stream()
        logger.info("Streaming stopped")

    def is_streaming(self) -> bool:
        if not self._client:
            return False
        status = self._client.get_stream_status()
        return status.output_active

    def set_scene(self, scene_name: str):
        if not self._client:
            raise ConnectionError("Not connected to OBS")
        self._client.set_current_program_scene(scene_name)
        logger.info("Switched to scene: %s", scene_name)

    def get_scenes(self) -> list[str]:
        if not self._client:
            return []
        resp = self._client.get_scene_list()
        return [s["sceneName"] for s in resp.scenes]

    def set_source_visibility(self, scene: str, source: str, visible: bool):
        if not self._client:
            raise ConnectionError("Not connected to OBS")
        scene_item_id = self._client.get_scene_item_id(scene, source).scene_item_id
        self._client.set_scene_item_enabled(scene, scene_item_id, visible)

    def set_text(self, source_name: str, text: str):
        """Update a GDI+ or FreeType2 text source."""
        if not self._client:
            raise ConnectionError("Not connected to OBS")
        self._client.set_input_settings(source_name, {"text": text}, overlay=True)

    def get_audio_sources(self) -> list[dict]:
        if not self._client:
            return []
        inputs = self._client.get_input_list()
        return [{"name": i["inputName"], "kind": i["inputKind"]} for i in inputs.inputs]
