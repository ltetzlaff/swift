// Uses Foundation on purpose: statically linking FoundationEssentials is what
// broke on Swift 6.4.0 (missing Synchronization/_FoundationCollections symbols),
// and a Foundation-free fixture let that ship.
import Foundation

struct Greeting: Codable { let text: String }

let data = try JSONEncoder().encode(Greeting(text: "hello from swift"))
print(try JSONDecoder().decode(Greeting.self, from: data).text)
