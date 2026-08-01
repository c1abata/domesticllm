import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ClientHardeningTests(unittest.TestCase):
    def test_repl_uses_libcurl_without_shell_or_temp_payload(self):
        source = (ROOT / "src" / "localai-repl.c").read_text(encoding="utf-8")
        self.assertIn("#include <curl/curl.h>", source)
        self.assertIn("CURLOPT_HTTPHEADER", source)
        self.assertNotIn("system(", source)
        self.assertNotIn("mkstemp", source)
        self.assertNotIn("jq ", source)
        self.assertIn("if (c < 0x20)", source)
        self.assertIn("umask(0077)", source)
        self.assertIn("chmod(HISTORY_FILE, S_IRUSR | S_IWUSR)", source)
        self.assertIn('getenv("LOCAL_AI_REQUEST_MODEL")', source)
        self.assertNotIn('"model\":\"local-main', source)

    def test_repl_build_is_strict_and_links_libcurl(self):
        build = (ROOT / "scripts" / "21_build_local_repl.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("-Werror", build)
        self.assertIn("-lcurl", build)

    def test_opencode_profiles_reference_only_environment_secret(self):
        for path in sorted((ROOT / "opencode").glob("*.json")):
            with self.subTest(path=path.name):
                profile = json.loads(path.read_text(encoding="utf-8"))
                providers = profile.get("provider", {})
                for provider in providers.values():
                    self.assertEqual(
                        provider.get("options", {}).get("apiKey"),
                        "{env:LOCAL_AI_API_KEY}",
                    )
                self.assertNotIn("mcp", profile)
                if path.name == "opencode.ds4-intel-lan.json":
                    limits = providers["ds4-local"]["models"]["ds4flash"]["limit"]
                    self.assertEqual(limits, {"context": 100000, "output": 32768})

    def test_powershell_does_not_accept_or_serialize_a_key(self):
        client = (ROOT / "scripts" / "local-ai-client.ps1").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("[string]$ApiKey", client)
        self.assertNotIn("-ApiKey", client)
        self.assertIn("baseURL = '{env:LOCAL_AI_BASE_URL}'", client)
        self.assertIn("apiKey = '{env:LOCAL_AI_API_KEY}'", client)
        self.assertIn("context = 100000; output = 32768", client)
        self.assertIn("[Uri]::TryCreate", client)


if __name__ == "__main__":
    unittest.main()
