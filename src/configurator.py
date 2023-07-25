import argparse
import json
from argparse import Namespace
from typing import Any, Mapping, Dict


class Configurator:
    def __init__(self):
        self.shell_parser = None
        self.bul_parser = None
        self.ck_parser = None
        self.args = None
        self.compiler_args = None

        self.parser = argparse.ArgumentParser(
            prog="aggregate",
            description="This script generate and test code on some platforms",
        )

        self.sub_parser = self.parser.add_subparsers(
            required=True,
            title="analyze and summarize",
            help="aggregate is shell above: analyze (code generator + profiler), summarize",
            dest="name_of_subparsers",
            metavar="utility {aggregate, analyze, summarize}",
        )

    def parse_sub_parsers(self, settings: Mapping[str, Any]):
        self.bul_parser = settings["analyze"].add_sub_parser(self.sub_parser)
        self.ck_parser = settings["summarize"].add_sub_parser(self.sub_parser)
        self.shell_parser = settings["aggregate"].add_sub_parser(self.sub_parser)
        self.bul_parser.set_defaults(utility=settings["analyze"])
        self.ck_parser.set_defaults(utility=settings["summarize"])
        self.shell_parser.set_defaults(utility=settings["aggregate"])
        return self.parser.parse_known_args()

    def configurate(self, settings: Mapping[str, Any] = None) -> Namespace:
        if settings is None:
            settings = {}
        self.args = self.parse_sub_parsers(settings)[0]
        config = self.read_cfg_file(
            self.args.config_file,
            self.args.section_in_config if hasattr(self.args, "section_in_config") else None,
        )

        return Namespace(**{**vars(self.args), **settings, **config})

    def read_cfg_file(self, config_file: str, section: str = None) -> Dict[str, Any]:
        if config_file is None:
            return dict()
        with open(config_file, mode="r") as f:
            config: Dict[str, Any] = json.load(f)
        return config if section is None else {**config["DEFAULT"], **config[section]}
