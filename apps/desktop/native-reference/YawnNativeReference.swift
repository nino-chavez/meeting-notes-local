import SwiftUI

// A native composition reference, not a replacement application. It carries no
// capture, persistence, search, or deletion authority. Its only job is to show
// the platform ceiling for the same meeting-reading encounter.

private struct Meeting: Identifiable, Hashable {
    let id: String
    let title: String
    let date: String
    let note: String
}

private enum AppSection: String, CaseIterable, Identifiable {
    case meetings = "Meetings"
    case ask = "Ask"
    case actions = "Actions"

    var id: String { rawValue }

    var symbol: String {
        switch self {
        case .meetings: return "text.page"
        case .ask: return "magnifyingglass"
        case .actions: return "checkmark.circle"
        }
    }
}

private let referenceMeetings = [
    Meeting(
        id: "acme",
        title: "Acme pilot planning",
        date: "Yesterday, 8:50 PM",
        note: "Use Acme for the pilot if legal clears the sample data."
    ),
    Meeting(
        id: "weekly",
        title: "Weekly product check-in",
        date: "Thursday, 8:30 PM",
        note: "Confirm the onboarding copy before the next build."
    ),
    Meeting(
        id: "intake",
        title: "Customer intake",
        date: "Tuesday, 9:30 PM",
        note: "Waiting for consent before recording."
    ),
]

@main
private struct YawnNativeReferenceApp: App {
    var body: some Scene {
        WindowGroup {
            YawnReferenceView()
                .frame(minWidth: 860, minHeight: 560)
        }
        .defaultSize(width: 1000, height: 680)
        .windowToolbarStyle(.unified)
        .commands {
            SidebarCommands()
        }
    }
}

private struct YawnReferenceView: View {
    @State private var section: AppSection? = .meetings
    @State private var meeting: Meeting? = referenceMeetings[1]
    @State private var detailTab = "Note"
    @State private var recording = false

    var body: some View {
        NavigationSplitView {
            List(selection: $section) {
                Section {
                    ForEach(AppSection.allCases) { item in
                        Label(item.rawValue, systemImage: item.symbol)
                            .tag(Optional(item))
                    }
                }

                Section("Folders") {
                    Label("All meetings", systemImage: "tray.full")
                    Label("Unfiled", systemImage: "archivebox")
                }
            }
            .navigationTitle("Yawn")
            .navigationSplitViewColumnWidth(min: 168, ideal: 188, max: 230)
        } content: {
            List(referenceMeetings, selection: $meeting) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.title)
                        .fontWeight(.medium)
                        .lineLimit(1)
                    Text(item.date)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
                .tag(Optional(item))
            }
            .navigationTitle("Meetings")
            .navigationSplitViewColumnWidth(min: 220, ideal: 250, max: 320)
        } detail: {
            if let meeting {
                MeetingReferenceDetail(meeting: meeting, selectedTab: $detailTab)
            } else {
                ContentUnavailableView(
                    "Choose a meeting",
                    systemImage: "text.page",
                    description: Text("Select a meeting to read its note and transcript.")
                )
            }
        }
        .navigationSplitViewStyle(.balanced)
        .tint(Color(red: 0.55, green: 0.25, blue: 0.21))
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Label(recording ? "Recording" : "Ready", systemImage: recording ? "record.circle.fill" : "circle")
                    .foregroundStyle(recording ? Color.green : Color.secondary)

                Button {
                    recording.toggle()
                } label: {
                    Label(recording ? "Stop" : "Record", systemImage: recording ? "stop.fill" : "waveform")
                }
                .keyboardShortcut("r", modifiers: [.command, .shift])

                Menu {
                    Button("Export Note", systemImage: "square.and.arrow.up") { }
                    Button("Meeting Details", systemImage: "info.circle") { detailTab = "Details" }
                } label: {
                    Label("More", systemImage: "ellipsis.circle")
                }
            }
        }
    }
}

private struct MeetingReferenceDetail: View {
    let meeting: Meeting
    @Binding var selectedTab: String
    private let tabs = ["Note", "Transcript", "Evidence", "Details"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text(meeting.title)
                    .font(.system(size: 28, weight: .semibold))
                    .tracking(-0.5)

                Text("An automatic note is a reading aid. Open the transcript to check the exact words.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.top, 7)

                Picker("Meeting view", selection: $selectedTab) {
                    ForEach(tabs, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(maxWidth: 430)
                .padding(.top, 24)

                Divider().padding(.top, 18)

                Group {
                    switch selectedTab {
                    case "Transcript": transcript
                    case "Evidence": evidence
                    case "Details": details
                    default: note
                    }
                }
                .padding(.top, 24)
            }
            .frame(maxWidth: 680, alignment: .leading)
            .padding(.horizontal, 42)
            .padding(.vertical, 36)
        }
        .background(Color(nsColor: .textBackgroundColor))
        .navigationTitle(meeting.title)
    }

    private var note: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Your note").font(.headline)
                Text(meeting.note)
                Text("Written during the meeting and kept with its transcript.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Divider()

            ClaimRow(kind: "Decision", text: "The team will keep the first-run flow to three steps.")
            ClaimRow(kind: "Action", text: "Review the first-run copy before Tuesday.")
        }
    }

    private var transcript: some View {
        VStack(alignment: .leading, spacing: 18) {
            TranscriptRow(speaker: "You", time: "08:14", text: "Let’s keep first run to three steps. Anything else can wait until after the first successful note.")
            Divider()
            TranscriptRow(speaker: "Other side", time: "08:37", text: "I’ll review the first-run copy before Tuesday and flag anything unclear.")
        }
    }

    private var evidence: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Decision in note").font(.caption).foregroundStyle(.secondary)
            Text("The team will keep the first-run flow to three steps.").font(.headline)
            Text("“Let’s keep first run to three steps. Anything else can wait until after the first successful note.”")
                .textSelection(.enabled)
            Label("Transcript · You · 08:14", systemImage: "quote.bubble")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var details: some View {
        Form {
            LabeledContent("Stored", value: "On this Mac")
            LabeledContent("Transcript", value: "Retained")
            LabeledContent("Recording audio", value: "Delete after 7 days")
        }
        .formStyle(.grouped)
    }
}

private struct ClaimRow: View {
    let kind: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(kind.uppercased())
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(text)
                .font(.body)
            Button("Show exact words") { }
                .controlSize(.small)
        }
    }
}

private struct TranscriptRow: View {
    let speaker: String
    let time: String
    let text: String

    var body: some View {
        Grid(alignment: .topLeading, horizontalSpacing: 18) {
            GridRow {
                VStack(alignment: .leading, spacing: 3) {
                    Text(speaker).fontWeight(.medium)
                    Text(time).font(.caption).foregroundStyle(.secondary)
                }
                Text(text)
                    .textSelection(.enabled)
            }
        }
    }
}
