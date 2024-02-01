import unittest

from dmod.core import restorable

from ...metrics import QueueCommunicator
from ...metrics import CommunicatorGroup


class MetricCommunicationTest(unittest.TestCase):
    def test_communicator(self):
        info_container = []
        error_container = []
        communicator = QueueCommunicator(
            "test_communicator",
            handlers={
                "info": lambda info_message: info_container.append(info_message),
                "error": lambda error_message: error_container.append(error_message)
            }
        )

        messages = ["This", "odd", "is", "odd", "a", "odd", "message"]

        for index, message in enumerate(messages):
            communicator.info(message, publish=index % 2 == 0)

        self.assertEqual(" ".join(info_container), "This is a message")

        written_messages = [message for message in communicator.get_info()]

        self.assertListEqual(messages, written_messages)

        errors = ["even", "here", "even", "lies", "even", "an", "even", "error"]

        for index, message in enumerate(errors):
            communicator.error(message, publish=index % 2 == 1)

        self.assertEqual(" ".join(error_container), "here lies an error")

        written_errors = [message for message in communicator.get_errors()]

        self.assertListEqual(errors, written_errors)

        package = communicator.package_instance()

        self.assertIsNotNone(package)

        restored_package = restorable.restore_value(package)

        self.assertIsNotNone(restored_package)


    def test_communicator_group(self):
        ...


if __name__ == '__main__':
    unittest.main()
