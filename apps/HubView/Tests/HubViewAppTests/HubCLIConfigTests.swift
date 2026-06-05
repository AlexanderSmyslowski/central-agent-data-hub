import Testing
@testable import HubViewApp
import Foundation

@Test
func commandLineConfigReadsExplicitFlags() {
    let config = HubCLIConfig(
        repoRoot: "/repo",
        pythonBin: "/python",
        databaseURL: "postgres://db",
        obsidianExportDir: "/obsidian"
    )

    #expect(config.repoRoot == "/repo")
    #expect(config.pythonBin == "/python")
    #expect(config.databaseURL == "postgres://db")
    #expect(config.obsidianExportDir == "/obsidian")
}

@Test
func bundledRuntimeConfigDecodesExpectedFields() {
    let data = Data(
        """
        {
          "repoRoot": "/repo",
          "pythonBin": "/python",
          "databaseURL": "postgres://db",
          "obsidianExportDir": "/vault"
        }
        """.utf8
    )

    let config = HubCLIConfig.decodeBundledRuntimeConfig(from: data)

    #expect(config?.repoRoot == "/repo")
    #expect(config?.pythonBin == "/python")
    #expect(config?.databaseURL == "postgres://db")
    #expect(config?.obsidianExportDir == "/vault")
}
