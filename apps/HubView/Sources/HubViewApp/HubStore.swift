import Foundation
import SwiftUI

@MainActor
final class HubStore: ObservableObject {
    @Published var projects: [ProjectSummary] = []
    @Published var selectedProjectID: ProjectSummary.ID?
    @Published var detail: HubViewModel?
    @Published var preview: WikiPreviewDocument?
    @Published var errorMessage: String?
    @Published var isLoadingProjects = false
    @Published var isLoadingDetail = false

    private let cli: HubCLI
    let wikiLinks: WikiLinkResolver

    init(cli: HubCLI) {
        self.cli = cli
        self.wikiLinks = WikiLinkResolver(exportDir: cli.config.obsidianExportDir)
    }

    func load() async {
        isLoadingProjects = true
        defer { isLoadingProjects = false }

        do {
            let projects = try await Task.detached(priority: .userInitiated) {
                try self.cli.fetchProjects()
            }.value
            self.projects = projects
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadSelectedProject() async {
        guard let projectID = selectedProjectID else {
            detail = nil
            preview = nil
            isLoadingDetail = false
            return
        }
        isLoadingDetail = true

        do {
            let detail = try await Task.detached(priority: .userInitiated) {
                try self.cli.fetchProjectView(slug: projectID)
            }.value
            guard selectedProjectID == projectID else {
                return
            }
            self.detail = detail
            errorMessage = nil
        } catch {
            guard selectedProjectID == projectID else {
                return
            }
            errorMessage = error.localizedDescription
        }
        if selectedProjectID == projectID {
            isLoadingDetail = false
        }
    }

    func reload() async {
        await load()
        await loadSelectedProject()
    }

    func selectProject(_ projectID: ProjectSummary.ID) {
        guard selectedProjectID != projectID else {
            return
        }
        selectedProjectID = projectID
        detail = nil
        preview = nil
        errorMessage = nil
        isLoadingDetail = true
    }

    func showHome() {
        selectedProjectID = nil
        detail = nil
        preview = nil
        errorMessage = nil
        isLoadingDetail = false
    }

    func showPreview(title: String, kind: String, url: URL?) {
        preview = WikiPreviewLoader.load(title: title, kind: kind, url: url)
    }

    func clearPreview() {
        preview = nil
    }
}
