import ArgumentParser

struct Locked: ParsableCommand {
    func run() { print("hello from a locked package") }
}

Locked.main()
