import configparser
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class EntrypointTest(unittest.TestCase):
    def run_entrypoint(self, overrides=None):
        env = {key: value for key, value in os.environ.items() if not key.startswith("SNELL_")}
        env["SNELL_PSK"] = "example-test-psk-32-characters"
        env.update(overrides or {})
        with tempfile.TemporaryDirectory(prefix="snell-entrypoint-") as temp:
            config_path = Path(temp) / "snell-server.conf"
            stub = Path(temp) / "snell-server"
            stub.write_text('#!/bin/bash\n[ "$1" = "-c" ] && [ -s "$2" ]\n')
            stub.chmod(0o755)
            script = Path("entrypoint.sh").read_text().replace(
                "/etc/snell-server/snell-server.conf", str(config_path)
            ).replace("/usr/bin/snell-server", str(stub))
            result = subprocess.run(
                ["bash", "-c", script], env=env, check=True,
                text=True, capture_output=True, timeout=10,
            )
            config = configparser.ConfigParser(interpolation=None)
            config.read(config_path)
        return dict(config["snell-server"]), result.stdout

    def test_defaults(self):
        config, output = self.run_entrypoint()
        self.assertEqual(config["listen"], "0.0.0.0:7177,[::]:7177")
        self.assertEqual(config["mode"], "default")
        self.assertNotIn("ipv6", config)
        self.assertEqual(config["psk"], "example-test-psk-32-characters")
        self.assertNotIn("dns", config)
        self.assertNotIn("dns-ip-preference", config)
        self.assertNotIn("egress-interface", config)
        self.assertNotIn("Generated PSK", output)

    def test_listen_addresses(self):
        for listen in ["0.0.0.0:7177", "[::1]:7177", "0.0.0.0:7177,[::]:7177"]:
            with self.subTest(listen=listen):
                config, _ = self.run_entrypoint({"SNELL_LISTEN": listen})
                self.assertEqual(config["listen"], listen)

    def test_modes(self):
        for mode in ["default", "unshaped", "unsafe-raw"]:
            with self.subTest(mode=mode):
                config, _ = self.run_entrypoint({"SNELL_MODE": mode})
                self.assertEqual(config["mode"], mode)

    def test_dns_ip_preferences(self):
        for preference in ["default", "prefer-ipv4", "prefer-ipv6", "ipv4-only", "ipv6-only"]:
            with self.subTest(preference=preference):
                config, _ = self.run_entrypoint({"SNELL_DNS_IP_PREFERENCE": preference})
                self.assertEqual(config["dns-ip-preference"], preference)

    def test_custom_dns_and_egress_interface(self):
        config, _ = self.run_entrypoint({
            "SNELL_DNS": "1.1.1.1,2606:4700:4700::1111", "SNELL_EGRESS_INTERFACE": "eth0",
        })
        self.assertEqual(config["dns"], "1.1.1.1,2606:4700:4700::1111")
        self.assertEqual(config["egress-interface"], "eth0")

    def test_empty_options_fall_back_to_defaults(self):
        config, _ = self.run_entrypoint({
            "SNELL_LISTEN": "", "SNELL_MODE": "", "SNELL_DNS": "",
            "SNELL_DNS_IP_PREFERENCE": "", "SNELL_EGRESS_INTERFACE": "",
        })
        self.assertEqual(config["listen"], "0.0.0.0:7177,[::]:7177")
        self.assertEqual(config["mode"], "default")
        self.assertNotIn("dns", config)
        self.assertNotIn("dns-ip-preference", config)
        self.assertNotIn("egress-interface", config)

    def test_random_psk_is_used_and_reported(self):
        config, output = self.run_entrypoint({"SNELL_PSK": ""})
        self.assertRegex(config["psk"], r"^[a-zA-Z0-9]{16}$")
        self.assertIn(f'Generated PSK: {config["psk"]}', output)


if __name__ == "__main__":
    unittest.main()
