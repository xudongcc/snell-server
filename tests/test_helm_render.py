import json
import subprocess
import tempfile
import unittest
from base64 import b64decode
from pathlib import Path


DEPENDENCY_BUILT = False
SNELL_VERSION = "6.0.0"
CHART_VERSION = "0.0.5"


def ensure_dependencies():
    global DEPENDENCY_BUILT
    if DEPENDENCY_BUILT:
        return
    if not list(Path("helm/charts").glob("common-*.tgz")):
        subprocess.run(["helm", "dependency", "build", "helm"], check=True)
    DEPENDENCY_BUILT = True


def render_chart(extra_args=None):
    ensure_dependencies()

    helm_command = [
        "helm",
        "template",
        "snell-server",
        "helm",
        "--namespace",
        "snell-server",
    ]
    if extra_args:
        helm_command.extend(extra_args)

    helm_result = subprocess.run(
        helm_command,
        check=True,
        capture_output=True,
        text=True,
    )
    yq_result = subprocess.run(
        [
            "yq",
            "eval-all",
            "-o=json",
            ". as $item ireduce ([]; . + [$item])",
            "-",
        ],
        input=helm_result.stdout,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        doc
        for doc in json.loads(yq_result.stdout)
        if isinstance(doc, dict) and doc.get("kind")
    ]


def by_kind_name(manifests, kind, name):
    for manifest in manifests:
        if (
            manifest.get("kind") == kind
            and manifest.get("metadata", {}).get("name") == name
        ):
            return manifest
    raise AssertionError(f"{kind}/{name} was not rendered")


def container_by_name(pod_spec, name):
    for container in pod_spec["containers"]:
        if container.get("name") == name:
            return container
    raise AssertionError(f"container {name} was not rendered")


def env_value(container, name):
    for env in container["env"]:
        if env.get("name") == name:
            return env.get("value")
    raise AssertionError(f"env var {name} was not rendered")


class HelmRenderTest(unittest.TestCase):
    def test_release_version_references_are_current(self):
        chart_app_version = subprocess.run(
            ["yq", ".appVersion", "helm/Chart.yaml"],
            check=True,
            capture_output=True,
            text=True,
        )
        chart_version = subprocess.run(
            ["yq", ".version", "helm/Chart.yaml"],
            check=True,
            capture_output=True,
            text=True,
        )
        values_image_tag = subprocess.run(
            ["yq", ".snellServer.image.tag", "helm/values.yaml"],
            check=True,
            capture_output=True,
            text=True,
        )
        workflow_matrix_versions = subprocess.run(
            ["yq", ".jobs.build.strategy.matrix.version[]", ".github/workflows/ci.yml"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(chart_app_version.stdout.strip(), SNELL_VERSION)
        self.assertEqual(chart_version.stdout.strip(), CHART_VERSION)
        self.assertEqual(values_image_tag.stdout.strip(), SNELL_VERSION)
        self.assertEqual(workflow_matrix_versions.stdout.splitlines(), [SNELL_VERSION])
        self.assertIn(
            f"ARG VERSION={SNELL_VERSION}", Path("Dockerfile").read_text()
        )
        self.assertIn(
            "helm package ./helm --dependency-update",
            Path(".github/workflows/ci.yml").read_text(),
        )

    def test_values_do_not_duplicate_traefik_host_sni_default(self):
        result = subprocess.run(
            ["yq", ".traefik.ingressRouteTCP | has(\"hostSNI\")", "helm/values.yaml"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "false")

    def test_secret_defaults_are_placeholder_values(self):
        manifests = render_chart()

        secret = by_kind_name(manifests, "Secret", "snell-server")

        self.assertEqual(
            b64decode(secret["data"]["SNELL_PSK"]).decode(),
            "please-change-me",
        )
        self.assertEqual(
            b64decode(secret["data"]["SHADOW_TLS_PASSWORD"]).decode(), "changeme"
        )

    def test_invalid_psks_fail_during_rendering(self):
        for psk in ["", "changeme", "a" * 11, "a" * 256, "密" * 3, "密" * 86, 123456789012, False, None]:
            with self.subTest(psk_type=type(psk).__name__, length=len(psk) if isinstance(psk, str) else None):
                with tempfile.TemporaryDirectory(prefix="snell-invalid-psk-") as temp:
                    values = Path(temp) / "values.json"
                    values.write_text(json.dumps({"snellServer": {"psk": psk}}))
                    with self.assertRaises(subprocess.CalledProcessError) as error:
                        render_chart(["--values", str(values)])
                self.assertIn("snellServer.psk", error.exception.stderr)
                self.assertIn("12 to 255 bytes", error.exception.stderr)

    def test_psk_byte_length_boundaries_are_accepted(self):
        for psk in ["a" * 12, "a" * 255, "密" * 4, "密" * 85]:
            with self.subTest(byte_length=len(psk.encode())):
                manifests = render_chart(["--set-string", f"snellServer.psk={psk}"])
                secret = by_kind_name(manifests, "Secret", "snell-server")
                self.assertEqual(b64decode(secret["data"]["SNELL_PSK"]).decode(), psk)
                daemonset = by_kind_name(manifests, "DaemonSet", "snell-server")
                container = container_by_name(daemonset["spec"]["template"]["spec"], "snell-server")
                self.assertEqual(env_value(container, "SNELL_PSK"), psk)

    def test_daemonset_defaults_to_pod_network_with_expected_ports(self):
        manifests = render_chart()

        daemonset = by_kind_name(manifests, "DaemonSet", "snell-server")
        pod_spec = daemonset["spec"]["template"]["spec"]
        snell_server = container_by_name(pod_spec, "snell-server")
        shadow_tls = container_by_name(pod_spec, "shadow-tls")

        self.assertEqual(
            snell_server["image"], f"ghcr.io/xudongcc/snell-server:{SNELL_VERSION}"
        )
        self.assertFalse(pod_spec["hostNetwork"])
        self.assertEqual(pod_spec["dnsPolicy"], "Default")
        self.assertEqual(env_value(snell_server, "SNELL_LISTEN"), "[::1]:7177")
        self.assertEqual(env_value(snell_server, "SNELL_MODE"), "default")
        self.assertTrue(
            {"SNELL_HOST", "SNELL_PORT", "SNELL_IPV6", "SNELL_DNS", "SNELL_DNS_IP_PREFERENCE", "SNELL_EGRESS_INTERFACE"}.isdisjoint(
                env["name"] for env in snell_server["env"]
            )
        )
        self.assertEqual(env_value(shadow_tls, "LISTEN"), "::0:8443")
        self.assertEqual(env_value(shadow_tls, "SERVER"), "::1:7177")
        self.assertEqual(env_value(shadow_tls, "TLS"), "gateway.icloud.com")
        self.assertEqual(env_value(shadow_tls, "FASTOPEN"), "1")
        self.assertEqual(
            env_value(shadow_tls, "MONOIO_FORCE_LEGACY_DRIVER"), "1"
        )
        self.assertIn(
            {"name": "tcp-7177", "containerPort": 7177, "protocol": "TCP"},
            snell_server["ports"],
        )
        self.assertIn(
            {"name": "udp-7177", "containerPort": 7177, "protocol": "UDP"},
            snell_server["ports"],
        )
        self.assertIn(
            {"name": "shadow-tls", "containerPort": 8443, "protocol": "TCP"},
            shadow_tls["ports"],
        )

    def test_snell_v6_environment_overrides(self):
        overrides = {
            "snellServer": {
                "listen": "127.0.0.1:7177,[::1]:7177",
                "mode": "unshaped",
                "dns": "1.1.1.1,2606:4700:4700::1111",
                "dnsIpPreference": "ipv4-only",
                "egressInterface": "eth0",
            }
        }
        with tempfile.TemporaryDirectory(prefix="snell-values-") as temp:
            values = Path(temp) / "values.json"
            values.write_text(json.dumps(overrides))
            manifests = render_chart(["--values", str(values)])
        daemonset = by_kind_name(manifests, "DaemonSet", "snell-server")
        snell_server = container_by_name(daemonset["spec"]["template"]["spec"], "snell-server")
        for name, value in {
            "SNELL_LISTEN": "127.0.0.1:7177,[::1]:7177",
            "SNELL_MODE": "unshaped",
            "SNELL_DNS": "1.1.1.1,2606:4700:4700::1111",
            "SNELL_DNS_IP_PREFERENCE": "ipv4-only",
            "SNELL_EGRESS_INTERFACE": "eth0",
        }.items():
            with self.subTest(name=name):
                self.assertEqual(env_value(snell_server, name), value)

    def test_default_listen_follows_chart_port(self):
        manifests = render_chart(["--set", "snellServer.port=17177"])
        daemonset = by_kind_name(manifests, "DaemonSet", "snell-server")
        containers = daemonset["spec"]["template"]["spec"]
        snell_server = container_by_name(containers, "snell-server")
        shadow_tls = container_by_name(containers, "shadow-tls")
        self.assertEqual(env_value(snell_server, "SNELL_LISTEN"), "[::1]:17177")
        self.assertEqual(env_value(shadow_tls, "SERVER"), "::1:17177")
        self.assertIn(
            {"name": "tcp-17177", "containerPort": 17177, "protocol": "TCP"},
            snell_server["ports"],
        )

    def test_shadow_tls_can_use_io_uring(self):
        manifests = render_chart(
            ["--set", "shadowTLS.forceLegacyDriver=false"]
        )

        daemonset = by_kind_name(manifests, "DaemonSet", "snell-server")
        shadow_tls = container_by_name(
            daemonset["spec"]["template"]["spec"], "shadow-tls"
        )

        self.assertNotIn(
            "MONOIO_FORCE_LEGACY_DRIVER",
            [env["name"] for env in shadow_tls["env"]],
        )

    def test_service_routes_shadowtls_through_traefik(self):
        manifests = render_chart()

        service = by_kind_name(manifests, "Service", "snell-server")
        ingress_route = by_kind_name(
            manifests, "IngressRouteTCP", "snell-server-8443"
        )

        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(service["spec"]["internalTrafficPolicy"], "Local")
        self.assertEqual(
            service["spec"]["selector"],
            {
                "app.kubernetes.io/instance": "snell-server",
                "app.kubernetes.io/name": "snell-server",
            },
        )
        self.assertNotIn(
            "tcp-7177", [port["name"] for port in service["spec"]["ports"]]
        )
        self.assertNotIn(
            "udp-7177", [port["name"] for port in service["spec"]["ports"]]
        )
        self.assertIn(
            {
                "name": "shadow-tls",
                "port": 8443,
                "targetPort": "shadow-tls",
                "protocol": "TCP",
            },
            service["spec"]["ports"],
        )
        self.assertEqual(ingress_route["spec"]["entryPoints"], ["websecure"])
        self.assertEqual(
            ingress_route["spec"]["routes"],
            [
                {
                    "match": "HostSNI(`gateway.icloud.com`)",
                    "services": [
                        {
                            "name": "snell-server",
                            "port": 8443,
                            "nativeLB": True,
                        }
                    ],
                }
            ],
        )
        self.assertEqual(ingress_route["spec"]["tls"], {"passthrough": True})

    def test_traefik_host_sni_defaults_to_shadowtls_sni(self):
        manifests = render_chart(["--set", "shadowTLS.sni=example.com"])

        daemonset = by_kind_name(manifests, "DaemonSet", "snell-server")
        shadow_tls = container_by_name(
            daemonset["spec"]["template"]["spec"], "shadow-tls"
        )
        ingress_route = by_kind_name(
            manifests, "IngressRouteTCP", "snell-server-8443"
        )

        self.assertEqual(env_value(shadow_tls, "TLS"), "example.com")
        self.assertEqual(
            ingress_route["spec"]["routes"][0]["match"], "HostSNI(`example.com`)"
        )

    def test_chart_is_installable_with_only_secret_overrides(self):
        manifests = render_chart(
            [
                "--set-string",
                "snellServer.psk=example-psk-at-least-12-bytes",
                "--set-string",
                "shadowTLS.password=example-shadow-password",
            ]
        )

        secret = by_kind_name(manifests, "Secret", "snell-server")
        ingress_route = by_kind_name(
            manifests, "IngressRouteTCP", "snell-server-8443"
        )

        self.assertEqual(
            b64decode(secret["data"]["SNELL_PSK"]).decode(), "example-psk-at-least-12-bytes"
        )
        self.assertEqual(
            b64decode(secret["data"]["SHADOW_TLS_PASSWORD"]).decode(),
            "example-shadow-password",
        )
        self.assertEqual(
            ingress_route["spec"]["routes"][0]["match"],
            "HostSNI(`gateway.icloud.com`)",
        )


if __name__ == "__main__":
    unittest.main()
