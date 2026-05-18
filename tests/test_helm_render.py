import json
import subprocess
import unittest
from base64 import b64decode
from pathlib import Path


DEPENDENCY_BUILT = False
SNELL_VERSION = "5.0.1"
CHART_VERSION = "0.0.3"


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
        workflow_matrix_version = subprocess.run(
            ["yq", ".jobs.build.strategy.matrix.version[0]", ".github/workflows/ci.yml"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(chart_app_version.stdout.strip(), SNELL_VERSION)
        self.assertEqual(chart_version.stdout.strip(), CHART_VERSION)
        self.assertEqual(values_image_tag.stdout.strip(), SNELL_VERSION)
        self.assertEqual(workflow_matrix_version.stdout.strip(), SNELL_VERSION)
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

        self.assertEqual(b64decode(secret["data"]["SNELL_PSK"]).decode(), "changeme")
        self.assertEqual(
            b64decode(secret["data"]["SHADOW_TLS_PASSWORD"]).decode(), "changeme"
        )

    def test_daemonset_defaults_to_pod_network_with_expected_ports(self):
        manifests = render_chart()

        daemonset = by_kind_name(manifests, "DaemonSet", "snell-server")
        pod_spec = daemonset["spec"]["template"]["spec"]
        snell_server = container_by_name(pod_spec, "snell-server")
        shadow_tls = container_by_name(pod_spec, "shadow-tls")

        self.assertFalse(pod_spec["hostNetwork"])
        self.assertEqual(pod_spec["dnsPolicy"], "Default")
        self.assertEqual(env_value(snell_server, "SNELL_PORT"), "6333")
        self.assertEqual(env_value(shadow_tls, "LISTEN"), "::0:8443")
        self.assertEqual(env_value(shadow_tls, "SERVER"), "::1:6333")
        self.assertEqual(env_value(shadow_tls, "TLS"), "gateway.icloud.com")
        self.assertEqual(env_value(shadow_tls, "FASTOPEN"), "1")
        self.assertIn(
            {"name": "tcp-6333", "containerPort": 6333, "protocol": "TCP"},
            snell_server["ports"],
        )
        self.assertIn(
            {"name": "udp-6333", "containerPort": 6333, "protocol": "UDP"},
            snell_server["ports"],
        )
        self.assertIn(
            {"name": "shadow-tls", "containerPort": 8443, "protocol": "TCP"},
            shadow_tls["ports"],
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
                "snellServer.psk=example-psk",
                "--set-string",
                "shadowTLS.password=example-shadow-password",
            ]
        )

        secret = by_kind_name(manifests, "Secret", "snell-server")
        ingress_route = by_kind_name(
            manifests, "IngressRouteTCP", "snell-server-8443"
        )

        self.assertEqual(
            b64decode(secret["data"]["SNELL_PSK"]).decode(), "example-psk"
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
