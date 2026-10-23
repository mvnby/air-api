"""In-memory IMAP protocol stub; never opens a network connection."""

class FakeImap:
    def __init__(self, count=5):
        self.validity = b"123"
        self.fetched = []
        self.count = count
        self.fail_uid = None
        self.oversized_uid = None
        self.folder = "INBOX"
        self.folder_counts = {}
        self.raw_overrides = {}

    def select(self, folder, readonly=False):
        assert readonly
        self.folder = folder
        return "OK", []

    def response(self, name):
        assert name == "UIDVALIDITY"
        return name, [self.validity]

    def uid(self, operation, *args):
        if operation == "SEARCH":
            # Deliberately return all UIDs: the client must discard <= cursor.
            return "OK", [b" ".join(str(n).encode() for n in range(1, self.folder_counts.get(self.folder, self.count) + 1))]
        uid = int(args[0])
        if uid == self.fail_uid:
            return "NO", []
        if args[-1] == "(RFC822.SIZE)":
            size = 31 * 1024 * 1024 if uid == self.oversized_uid else 100
            return "OK", [f"{uid} (RFC822.SIZE {size})".encode()]
        assert args[-1] == "(BODY.PEEK[])"
        self.fetched.append((self.folder, uid))
        raw = f"Message-ID: <{uid}@example.test>\nFrom: sender@example.test\nSubject: Letter {uid}\n\nBody {uid}".encode()
        return "OK", [(b"body", self.raw_overrides.get(uid, raw))]
