import json
from typing import Any, Dict, List


class Configurator:
    def configurate(self, args: Dict[str, Any]):
        config_file = args.get("config_file")
        section_in_config = args.get("section_in_config")

        if config_file:
            config = self.read_cfg_file(config_file, section_in_config)
            args.update(config)

    def read_cfg_file(self, config_file: str | None, section: str | None = None) -> Dict[str, Any]:
        if config_file is None:
            return dict()
        with open(config_file, mode="r") as f:
            config: Dict[str, Any] = json.load(f)
        return config if section is None else {**config["DEFAULT"], **config[section]}

    def get_true_settings(self, settings: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = settings
        for arg in args:
            if arg in settings:
                if args[arg] != settings[arg]:
                    settings[arg] = args[arg]
            else:
                settings[arg] = args[arg]
        return result

    def parse_args(self, args: List[str], default_params: Dict[str, Any]) -> Dict[str, Any]:
        for i in range(0, len(args), 2):
            key = args[i].lstrip("--").replace("-", "_")
            value = args[i + 1]
            if key in default_params:
                default_params[key] = value

        return default_params
