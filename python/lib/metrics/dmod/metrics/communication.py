from __future__ import annotations

import json
import multiprocessing
import typing
import os
import abc
import collections
import inspect
import enum
import logging
import traceback
from datetime import datetime
from queue import Empty

from dmod.core.restorable import Restorable

MESSAGE = typing.Union[bytes, str, typing.Dict[str, typing.Any], typing.Sequence, bool, int, float]
MESSAGE_HANDLER = typing.Callable[[MESSAGE], typing.NoReturn]
REASON_TO_WRITE = typing.Union[str, typing.Dict[str, typing.Any]]


class Verbosity(enum.IntEnum):
    """
    An enumeration detailing the density of information that may be transmitted, not to logs,
    but through things like streams and communicators
    """
    QUIET = enum.auto()
    """Emit very little information"""

    NORMAL = enum.auto()
    """Emit a baseline amount of information"""

    LOUD = enum.auto()
    """Emit a lot of detailed (often diagnostic) information"""

    ALL = enum.auto()
    """Emit everything, including raw data"""


class Communicator(Restorable):
    def __init__(
        self,
        communicator_id: str,
        verbosity: Verbosity = None,
        on_receive: typing.Union[MESSAGE_HANDLER, typing.Sequence[MESSAGE_HANDLER]] = None,
        handlers: typing.Dict[str, typing.Union[MESSAGE_HANDLER, typing.Sequence[MESSAGE_HANDLER]]] = None,
        include_timestamp: bool = None,
        timestamp_format: str = None,
        **kwargs
    ):
        self.__communicator_id = communicator_id
        self._handlers = collections.defaultdict(list)
        self._verbosity = verbosity or Verbosity.QUIET
        self.__include_timestamp = include_timestamp if include_timestamp is not None else False
        self.__timestamp_format = timestamp_format or "%Y-%m-%d %I:%M:%S %p %Z"

        if handlers:
            if not isinstance(handlers, typing.Mapping):
                raise ValueError(
                    f"The handlers object passed to the communicator for {communicator_id} was not some form of mapping"
                )

            for event_name, handler in handlers.items():
                self._register_handler(event_name, handler)

        if on_receive:
            self._register_handler('receive', on_receive)

        validation_messages = self._validate()

        if validation_messages:
            joined_messages = os.linesep + os.linesep.join(validation_messages)
            raise ValueError(f"Communication with {communicator_id} could not be established: {joined_messages}")

    def _register_handler(
        self,
        event_name: str,
        handlers: typing.Union[MESSAGE_HANDLER, typing.Sequence[MESSAGE_HANDLER]]
    ):
        """
        Register event handlers

        Args:
            event_name: The name of the event
            handlers: one or more handlers for said event
        """
        if isinstance(handlers, typing.Sequence) and handlers:
            for handler in handlers:
                if not isinstance(handler, typing.Callable):
                    raise ValueError(
                        f"A handler for {event_name} was passed for the communicator {self.communicator_id} was "
                        f"not a function"
                    )

                signature = inspect.signature(handler)
                if len(signature.parameters) == 0:
                    raise ValueError(
                        f"All event handlers for the {self.communicator_id} communicator must have "
                        f"at least one argument"
                    )
                self._handlers[event_name].append(handler)
        elif isinstance(handlers, typing.Callable):
            self._handlers[event_name].append(handlers)
        elif handlers is not None:
            raise ValueError(
                f"The item passed as a handler for the {event_name} event for the {self.communicator_id} "
                f"communicator cannot be used as a function"
            )

    def handle_event(self, event_name: str, message):
        for handler in self._handlers.get(event_name, []):
            try:
                handler(message)
            except Exception as error:
                error_message = f"Could not handle a message event for '{event_name}' through '{handler}'. " \
                                f"Message:{os.linesep}{message}"
                logging.error(error_message, error)

    @abc.abstractmethod
    def error(self, message: str, exception: Exception = None, verbosity: Verbosity = None, publish: bool = None):
        """
        Publishes an error to the communicator's set of error messages

        Args:
            message: The error message
            exception: An exception that caused the error
            verbosity: The significance of the message. If given, the message will only be recorded if the
                        vebosity matches or exceeds the communicator's verbosity
            publish: Whether to write the message to the channel
        """
        pass

    @abc.abstractmethod
    def write(self, reason: REASON_TO_WRITE, data: dict):
        """
        Writes data to the communicator

        Takes the form of:

        {
            "event": reason,
            "time": YYYY-mm-dd HH:MMz,
            "data": json string
        }

        Args:
            reason: The reason for data being written to the channel
            data: The data to write to the channel; will be converted to a string
        """
        ...

    @abc.abstractmethod
    def info(self, message: str, verbosity: Verbosity = None, publish: bool = None):
        """
        Publishes a message to the communicator's set of basic information.

        Data will look like the following when published to the channel:

            {
                "event": "info",

                "time": YYYY-mm-dd HH:MM z,

                "data": {
                    "info": message
                }
            }

        Args:
            message: The message to record
            verbosity: The significance of the message. If given, the message will only be recorded if the
                        verbosity matches or exceeds the communicator's verbosity
            publish: Whether the message should be published to the channel
        """
        pass

    @abc.abstractmethod
    def read_errors(self) -> typing.Iterable[str]:
        """
        Returns:
            All recorded error messages for this evaluation so far
        """
        pass

    @abc.abstractmethod
    def read_info(self) -> typing.Iterable[str]:
        """
        Returns:
            All basic notifications for this evaluation so far
        """
        pass

    @abc.abstractmethod
    def _validate(self) -> typing.Sequence[str]:
        """
        Returns:
            A list of issues with this communicator as constructed
        """
        pass

    @abc.abstractmethod
    def read(self) -> typing.Any:
        """
        Wait the communicator's set timeout for a message

        Returns:
            A deserialized message if one was received, Nothing otherwise
        """
        pass

    @property
    def include_timestamp(self) -> bool:
        """
        Whether to include the timestamp in communicated messages
        """
        return self.__include_timestamp

    @property
    def timestamp_format(self) -> str:
        """
        The format for timestamps in added to messages
        """
        return self.__timestamp_format

    @property
    def communicator_id(self) -> str:
        return self.__communicator_id

    @property
    def verbosity(self) -> Verbosity:
        """
        Returns:
            How verbose this communicator is
        """
        return self._verbosity


class QueueCommunicator(Communicator):
    def write(self, reason: REASON_TO_WRITE, data: dict):
        message = {
            "event": reason,
            "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M%z"),
            "data": data,
        }
        self.info(message=json.dumps(message), include_timestamp=False)

    def get_package_arguments(self) -> typing.List:
        return []

    def get_package_keyword_arguments(self) -> typing.Dict[str, typing.Any]:
        logging.warning(
            f"Getting package data from a '{self.__class__.__name__}' for ID: '{self.communicator_id}'. "
            f"This will not connect back to this when restored. "
            f"Avoid using this in any instance other than testing."
        )
        return {
            "communicator_id": self.communicator_id,
            "verbosity": self.verbosity,
            "information": self.get_info(),
            "errors": self.get_errors(),
            "maximum_size": self.__maximum_size,
            "operation_wait_seconds": self.__wait_seconds
        }

    def __init__(
        self,
        communicator_id: str,
        verbosity: Verbosity = None,
        handlers: typing.Dict[str, typing.Union[MESSAGE_HANDLER, typing.Sequence[MESSAGE_HANDLER]]] = None,
        information: typing.Iterable[str] = None,
        errors: typing.Iterable[str] = None,
        maximum_size: int = None,
        operation_wait_seconds: float = None,
        **kwargs
    ):
        if not isinstance(maximum_size, int) and isinstance(maximum_size, typing.SupportsFloat):
            maximum_size = int(float(maximum_size))
        if maximum_size is None or not isinstance(maximum_size, int) or maximum_size < 0:
            maximum_size = 0

        self.__lock = multiprocessing.RLock()
        self.__maximum_size = maximum_size
        self.__information = multiprocessing.Queue(maxsize=maximum_size)
        self.__errors = multiprocessing.Queue(maxsize=maximum_size)
        self.__wait_seconds = operation_wait_seconds if isinstance(operation_wait_seconds, (float, int)) else 5
        self.__information_count = 0
        self.__error_count = 0

        with self.__lock:
            for message in information or []:
                self.__information.put(message)
                self.__information_count += 1

        with self.__lock:
            for error in errors or []:
                self.__errors.put(error)
                self.__error_count += 1

        super().__init__(communicator_id=communicator_id, verbosity=verbosity, handlers=handlers, **kwargs)

    @property
    def error_count(self) -> int:
        with self.__lock:
            return self.__error_count

    @property
    def information_count(self) -> int:
        with self.__lock:
            return self.__information_count

    def error(
        self,
        message: str,
        exception: Exception = None,
        verbosity: Verbosity = None,
        publish: bool = None
    ):
        """
        Publishes an error to the communicator's set of error messages

        Args:
            message: The error message
            exception: An exception that caused the error
            verbosity: The significance of the message. If given, the message will only be recorded if the
                        verbosity matches or exceeds the communicator's verbosity
            publish: Whether to write the message to the channel
        """
        if verbosity and self.verbosity < verbosity:
            return

        if self.include_timestamp:
            timestamp = datetime.now().astimezone().strftime(self.timestamp_format)
            message = f"[{timestamp}] {message}"

        if exception:
            message += f"{os.linesep}{traceback.format_exc()}"

        put_try_count = 0
        max_attempts = 10

        logging.info(f"Adding an error. There are currently {self.error_count} items in the queue")

        with self.__lock:
            while put_try_count < max_attempts:
                try:
                    while self.__errors.full():
                        logging.info("There are too many entries in the error log. Trying to remove the oldest entry")
                        try:
                            last_message = self.__errors.get()
                            self.__error_count -= 1
                            logging.info(f"Removed: {last_message}")
                            self.handle_event("expire", last_message)
                        except BaseException as exception:
                            logging.error(f"Could not remove an item from the error log: {exception}")
                    self.__errors.put(message, block=True, timeout=self.__wait_seconds)
                    self.__error_count += 1
                except BaseException as exception:
                    put_try_count += 1

                    if put_try_count >= max_attempts:
                        raise Exception(f"Could not communicate error: {message}") from exception

                    logging.error(f"Failed to add an item into the error log: {exception}. Trying again.")
                else:
                    logging.info(f"Added '{message}' to the error log")
                    break

        if put_try_count >= max_attempts:
            raise Exception(f"Could not communicate error: {message} - ran out of attempts")

        if publish:
            self.handle_event("error", message)
        else:
            logging.info(f"Not publishing extra information about the newly added '{message}' error")

    def info(self, message: str, verbosity: Verbosity = None, publish: bool = None, include_timestamp: bool = None):
        """
        Publishes a message to the communicator's set of basic information.

        Args:
            message: The message to record
            verbosity: The significance of the message. If given, the message will only be recorded if the
                        verbosity matches or exceeds the communicator's verbosity
            publish: Whether the message should be published to the channel
        """
        if verbosity and self.verbosity < verbosity:
            return

        if include_timestamp is None:
            include_timestamp = self.include_timestamp

        if include_timestamp:
            timestamp = datetime.now().astimezone().strftime(self.timestamp_format)
            message = f"[{timestamp}] {message}"

        put_try_count = 0
        max_attempts = 10

        logging.info(f"Adding a message. There are currently {self.information_count} items in the queue")

        with self.__lock:
            while put_try_count < max_attempts:
                try:
                    while self.__information.full():
                        logging.info(
                            "There are too many entries in the information log. Trying to remove the oldest entry"
                        )
                        try:
                            last_message = self.__information.get()
                            self.__information_count -= 1
                            logging.info(f"Removed: {last_message}")
                            self.handle_event("expire", last_message)
                        except BaseException as exception:
                            logging.error(f"Could not remove an item from the information log: {exception}")
                    self.__information.put(message, block=True, timeout=self.__wait_seconds)
                    self.__information_count += 1
                except BaseException as exception:
                    put_try_count += 1

                    if put_try_count >= max_attempts:
                        raise Exception(f"Could not communicate information: {message}") from exception

                    logging.error(f"Failed to add an item into the information log: {exception}. Trying again.")
                else:
                    logging.info(f"Added '{message}' to the information log")
                    break

        if publish:
            self.handle_event("info", message)
        else:
            logging.info(f"Not publishing extra information about the newly added '{message}' message")

    def get_errors(self, enforce_length: bool = None) -> typing.Iterable[str]:
        enforce_length = bool(enforce_length) if enforce_length is not None else enforce_length

        errors = []

        with self.__lock:
            while not self.__errors.empty():
                error = None
                try:
                    error = self.__errors.get(block=True, timeout=self.__wait_seconds)
                    self.__error_count -= 1
                    logging.info(f"Read {error} from the error log")
                    errors.append(error)
                except Empty:
                    logging.info(f"There are no more errors to look for")
                    break
                except BaseException as exception:
                    logging.info(f"Could not get an error from the log: {exception}")
                    if error:
                        logging.info(f"Trying to put an error back: {error}")
                        try:
                            self.error(error)
                        except:
                            logging.info(f"Could not put {error} back into the error log")

                    raise exception

            for error in errors:
                logging.info(f"Putting {error} back into the error log")
                self.__errors.put(error, block=True, timeout=self.__wait_seconds)
                self.__error_count += 1

            if enforce_length:
                assert len(errors) == self.error_count

        return errors

    def get_info(self, enforce_length: bool = None) -> typing.Iterable[str]:
        enforce_length = bool(enforce_length) if enforce_length is not None else enforce_length

        messages = []

        with self.__lock:
            while not self.__information.empty():
                message = None
                try:
                    message = self.__information.get(block=True, timeout=self.__wait_seconds)
                    self.__information_count -= 1
                    messages.append(message)
                except TimeoutError:
                    continue
                except Empty:
                    break
                except BaseException as exception:
                    if message:
                        try:
                            self.info(message)
                        except:
                            pass
                    raise exception

            for message in messages:
                self.__information.put(message, block=True, timeout=self.__wait_seconds)
                self.__information_count += 1

            if enforce_length:
                assert len(messages) == self.information_count

        return messages

    def read_errors(self) -> typing.Iterable[str]:
        errors = []

        while not self.__errors.empty():
            error = None
            try:
                error = self.__errors.get(block=True, timeout=self.__wait_seconds)
                errors.append(error)
            except TimeoutError:
                continue
            except Empty:
                break
            except BaseException as exception:
                if error:
                    try:
                        self.error(error)
                    except:
                        pass
                raise exception

        for error in errors:
            self.handle_event("read_error", error)

        return errors

    def read_info(self) -> typing.Iterable[str]:
        info = []

        while not self.__information.empty():
            try:
                info.append(self.__information.get(block=True, timeout=self.__wait_seconds))
            except Empty:
                break

        return info

    def _validate(self) -> typing.Sequence[str]:
        pass

    def read(self) -> str:
        return self.__information.get(block=True)

    def __hash__(self):
        info = sorted(self.get_info())
        errors = sorted(self.get_errors())
        return hash(tuple([
            self.communicator_id,
            self.verbosity,
            info,
            errors,
            self.__maximum_size,
            self.__wait_seconds
        ]))

    def __eq__(self, other):
        if other is None:
            return False

        if not isinstance(other, self.__class__):
            return False

        return hash(self) == hash(other)


class CommunicatorGroup(typing.Mapping, Restorable):
    """
    A collection of Communicators clustered for group operations
    """

    def get_package_arguments(self) -> typing.List:
        return []

    def get_package_keyword_arguments(self) -> typing.Dict[str, typing.Any]:
        return {
            "communicators": {
                communicator_id: communicator.package_instance()
                for communicator_id, communicator in self.__communicators.items()
            }
        }

    def __getitem__(self, key: str) -> Communicator:
        return self.__communicators[key]

    def __len__(self) -> int:
        return len(self.__communicators)

    def __iter__(self) -> typing.Iterator[Communicator]:
        return iter(self.__communicators.values())

    def __contains__(self, key: typing.Union[str, Communicator]) -> bool:
        if isinstance(key, Communicator):
            return key in self.__communicators.values()

        return key in self.__communicators

    def __init__(
        self,
        communicators: typing.Union[
            Communicator,
            typing.Iterable[Communicator],
            typing.Mapping[str, Communicator],
            CommunicatorGroup
        ] = None
    ):
        """
        Constructor

        Args:
            communicators: Communicators to be used by the collection
        """
        if isinstance(communicators, CommunicatorGroup):
            self.__communicators = {

            }
        elif isinstance(communicators, typing.Mapping):
            self.__communicators: typing.Dict[str, Communicator] = {
                key: value
                for key, value in communicators.items()
            }
        elif isinstance(communicators, typing.Sequence):
            self.__communicators: typing.Dict[str, Communicator] = {
                communicator.communicator_id: communicator
                for communicator in communicators
            }
        elif isinstance(communicators, Communicator):
            self.__communicators = {
                communicators.communicator_id: communicators
            }
        else:
            self.__communicators: typing.Dict[str, Communicator] = dict()

    def attach(
        self,
        communicator: typing.Union[
            Communicator,
            typing.Sequence[Communicator],
            typing.Mapping[typing.Any, Communicator]
        ]
    ) -> int:
        """
        Adds one or more communicators to the collection

        Args:
            communicator: The communicator(s) to add

        Returns:
            The number of communicators now in the collection
        """
        if isinstance(communicator, typing.Mapping):
            self.__communicators: typing.Dict[str, Communicator] = {
                key: value
                for key, value in communicator.items()
            }
        elif isinstance(communicator, typing.Sequence):
            self.__communicators.update({
                communicator.communicator_id: communicator
                for communicator in communicator
            })
        elif isinstance(communicator, Communicator):
            self.__communicators[communicator.communicator_id] = communicator
        else:
            self.__communicators: typing.Dict[str, Communicator] = dict()

        return len(self.__communicators)

    def error(self, message: str, exception: Exception = None, verbosity: Verbosity = None, publish: bool = None):
        """
        Send an error to all communicators

        Args:
            message:
            exception:
            verbosity:
            publish:
        """
        if self.empty:
            logging.getLogger().error(message, exc_info=exception)

        for communicator in self.__communicators.values():
            communicator.error(
                message=message,
                exception=exception,
                verbosity=verbosity,
                publish=publish
            )

    def info(self, message: str, verbosity: Verbosity = None, publish: bool = None):
        """
        Send basic information to all communicators

        Args:
            message:
            verbosity:
            publish:
        """
        if self.empty:
            logging.log(level=logging.DEBUG, msg=message)

        for communicator in self.__communicators.values():
            communicator.info(message=message, verbosity=verbosity, publish=publish)

    def write(self, reason: REASON_TO_WRITE, data: dict, verbosity: Verbosity = None):
        """
        Write to all communicators

        If verbosity is passed, only communicators whose verbosity meets or exceeds the indicated
        verbosity will be written to

        Args:
            reason:
            data:
            verbosity:
        """
        try:
            for communicator in self.__communicators.values():
                if not verbosity or verbosity and communicator.verbosity >= verbosity:
                    communicator.write(reason=reason, data=data)
        except Exception as e:
            message = traceback.format_exc()

            # The message is also printed since logging sometimes forces all newlines into a single line with just
            # the "\n" character, making the error hard to read
            print(message)
            raise Exception(message) from e

    def update(self, communicator_id: str = None, **kwargs):
        """
        Update one or all communicators

        Args:
            communicator_id:
            **kwargs:
        """
        if communicator_id:
            communicator = self.__communicators[communicator_id]

            if hasattr(communicator, 'update'):
                communicator.update(**kwargs)
        else:
            for communicator in self.__communicators.values():
                if hasattr(communicator, 'update'):
                    communicator.update(**kwargs)

    def sunset(self, seconds: float = None):
        """
        Set an expiration for all communicators

        Args:
            seconds:
        """
        for communicator in self.__communicators.values():
            if hasattr(communicator, 'sunset'):
                communicator.sunset(seconds)

    def read_errors(self, *communicator_ids: str) -> typing.Iterable[str]:
        """
        Read all error messages from either a select few or all communicators

        Calling without communicator ids will result in all errors from all communicators

        Args:
            communicator_ids:

        Returns:
            All error messages
        """
        errors = set()

        if communicator_ids:
            for communicator_id in communicator_ids:
                errors.union({error for error in self.__communicators[communicator_id].read_errors()})
        else:
            for communicator in self.__communicators.values():
                errors.union(communicator.read_errors())

        return errors

    def read_info(self, *communicator_ids: str) -> typing.Iterable[str]:
        """
        Read all basic information from either a select few or all communicators

        Calling without communicator ids will result in all information from all communicators

        Args:
            communicator_ids:

        Returns:
            All information from the indicated communicators
        """
        information = set()

        if communicator_ids:
            communicators = [
                communicator
                for key, communicator in self.__communicators.items()
                if key in communicator_ids
            ]
            for communicator in communicators:
                information.union({message for message in communicator.read_info()})
        else:
            for communicator in self.__communicators.values():
                information.union(communicator.read_info())

        return information

    def read(self, communicator_id: str):
        """
        Read data from a specific communicator

        Args:
            communicator_id: The communicator to read from

        Returns:
            The read data
        """
        return self.__communicators[communicator_id].read()

    def send_all(self) -> bool:
        """
        Returns:
            True if there is a communicator that expects all data
        """
        return bool([
            communicator
            for communicator in self.__communicators.values()
            if communicator.verbosity == Verbosity.ALL
        ])

    def __str__(self):
        return f"Communicators: {', '.join([str(communicator) for communicator in self.__communicators])}"

    def __repr__(self):
        return self.__str__()

    @property
    def empty(self):
        return len(self.__communicators) == 0

    def copy(self) -> typing.Dict[str, Communicator]:
        return {
            communicator_id: communicator
            for communicator_id, communicator in self.__communicators.items()
        }
