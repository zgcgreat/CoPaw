# -*- coding: utf-8 -*-
from click.testing import CliRunner

from swe.cli.providers_cmd import models_group


def test_local_model_cli_commands_report_unsupported() -> None:
    runner = CliRunner()

    commands = [
        ["download", "repo/model"],
        ["local"],
        ["remove-local", "repo/model", "--yes"],
    ]

    for args in commands:
        result = runner.invoke(models_group, args)

        assert result.exit_code == 1
        assert (
            "Local model management is no longer supported." in result.output
        )
