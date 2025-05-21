from jobradar.notifiers.telegram import TelegramNotifier

if __name__ == "__main__":
    notifier = TelegramNotifier()
    class DummyJob:
        def __init__(self):
            self.title = "Test Job"
            self.company = "Test Company"
            self.source = "Test Source"
            self.url = "https://example.com/job"
    
    jobs = [DummyJob()]
    try:
        response = notifier.notify(jobs)
        print("Message sent!", response.status_code)
    except Exception as e:
        print("Failed to send message:", e) 