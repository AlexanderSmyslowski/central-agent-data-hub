import Foundation
import SwiftUI

@MainActor
final class HubStore: ObservableObject {
    @Published var projects: [ProjectSummary] = []
    @Published var selectedProjectID: ProjectSummary.ID?
    @Published var detail: HubViewModel?
    @Published var errorMessage: String?
    @Published var isLoadingProjects = false
    @Published var isLoadingDetail = false

    private let cli: HubCLI

    init(cli: HubCLI) {
        self.cli = cli
    }

    func load() async {
        isLoadingProjects = true
        defer { isLoadingProjects = false }

        do {
            let projects = try await Task.detached(priority: .userInitiated) {
                try self.cli.fetchProjects()
            }.value
            self.projects = projects
            if selectedProjectID == nil {
                selectedProjectID = projects.first?.id
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadSelectedProject() async {
        guard let selectedProjectID else {
            detail = nil
            return
        }
        isLoadingDetail = true
        defer { isLoadingDetail = false }

        do {
            let detail = try await Task.detached(priority: .userInitiated) {
                try self.cli.fetchProjectView(slug: selectedProjectID)
            }.value
            self.detail = detail
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func reload() async {
        await load()
        await loadSelectedProject()
    }
}
