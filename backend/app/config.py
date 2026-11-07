import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_path: str = 'backend/data/cqa.sqlite3'
    organizer_url: str = field(default='', repr=False)
    organizer_timeout: float = 20
    provider_kind: str = 'openai'
    provider_api_key: str = field(default='', repr=False)
    provider_model: str = 'gpt-5.4-mini-2026-03-17'
    provider_base_url: str = 'https://api.openai.com/v1'
    provider_timeout: float = 45
    max_output_tokens: int = 8000
    cors_origins: tuple[str, ...] = ('http://localhost:5173',)

    def __post_init__(self):
        if not 1 <= self.organizer_timeout <= 60:
            raise ValueError('Organizer timeout must be between 1 and 60 seconds')
        if not 1 <= self.provider_timeout <= 180:
            raise ValueError('Provider timeout must be between 1 and 180 seconds')
        if self.provider_kind not in ('openai', 'ollama'):
            raise ValueError('MODEL_PROVIDER must be openai or ollama')
        if not 256 <= self.max_output_tokens <= 16000:
            raise ValueError('MAX_OUTPUT_TOKENS must be between 256 and 16000')

    @classmethod
    def from_env(cls):
        return cls(
            database_path=os.getenv('DATABASE_PATH', cls.database_path),
            organizer_url=os.getenv('ORGANIZER_DATASET_URL', ''),
            organizer_timeout=float(os.getenv('ORGANIZER_TIMEOUT_SECONDS', '20')),
            provider_kind=os.getenv('MODEL_PROVIDER', 'openai').strip().lower(),
            provider_api_key=os.getenv('OPENAI_API_KEY', ''),
            provider_model=os.getenv('OPENAI_MODEL', cls.provider_model),
            provider_base_url=os.getenv('OPENAI_BASE_URL', cls.provider_base_url),
            provider_timeout=float(os.getenv('PROVIDER_TIMEOUT_SECONDS', '45')),
            max_output_tokens=int(os.getenv('MAX_OUTPUT_TOKENS', '8000')),
            cors_origins=tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if x.strip()),
        )
