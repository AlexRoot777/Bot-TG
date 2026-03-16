import logging
import secrets
import subprocess


class MTProtoService:
    def __init__(self, host: str, port: int, proxy_gen_cmd: str | None = None) -> None:
        self.host = host
        self.port = port
        self.proxy_gen_cmd = proxy_gen_cmd

    @staticmethod
    def _local_secret() -> str:
        return "dd" + secrets.token_hex(16)

    def _generate_secret(self) -> str:
        if not self.proxy_gen_cmd:
            return self._local_secret()

        try:
            out = subprocess.check_output(
                self.proxy_gen_cmd,
                shell=True,
                text=True,
                timeout=10,
            ).strip()
            if out:
                return out
            logging.warning("PROXY_GEN_CMD returned empty output, using local fallback")
        except (subprocess.SubprocessError, OSError) as exc:
            logging.warning("PROXY_GEN_CMD failed (%s), using local fallback", exc)

        return self._local_secret()

    def issue_key(self) -> tuple[str, str]:
        secret = self._generate_secret()
        uri = f"tg://proxy?server={self.host}&port={self.port}&secret={secret}"
        return secret, uri