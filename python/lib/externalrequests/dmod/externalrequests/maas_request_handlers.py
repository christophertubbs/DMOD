import logging
from abc import ABC, abstractmethod
from dmod.access import Authorizer
from dmod.communication import AbstractRequestHandler, FullAuthSession, MaaSRequest, \
    InitRequestResponseReason, InternalServiceClient, PartitionRequest, PartitionResponse, PartitionerServiceClient, \
    Session, SessionManager
from pathlib import Path
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s,%(msecs)d %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)


class MaaSRequestHandler(AbstractRequestHandler, ABC):
    """
    Abstraction of general handler for ::class:`MaaSRequest` instances.

    General handler type for externally initiated requests that, by implication, will require authorization in order to
    be handled.  The exception is auth requests themselves.  Such requests are modeled by the ::class:`MaaSRequest`
    type.
    """

    def __init__(self, session_manager: SessionManager, authorizer: Authorizer, service_host: str, service_port: int,
                 service_ssl_dir: Path):
        self._session_manager = session_manager
        self._authorizer = authorizer
        self._service_host = service_host
        self._service_port = service_port
        self._service_ssl_dir = service_ssl_dir
        self._service_url = None

    async def _is_authorized(self, request: MaaSRequest, session: FullAuthSession) -> bool:
        """
        Get whether this session is authorized for submitting the given request.

        Determine whether the initiating user/session for a received request is currently authorized to submit such a
        request for processing.

        Parameters
        ----------
        request : MaaSRequest
            The request to be considered.
        session : FullAuthSession
            The session for which to check permission.

        Returns
        -------
        bool
            Whether this session is authorized for submitting the given request.
        """
        # TODO: implement more completely (and implement actual authorizer)
        # TODO: in particular, finish implementation of utilized determine_required_access_types()
        required_access_types = await self.determine_required_access_types(request, session.user)
        for access_type in required_access_types:
            if not await self._authorizer.check_authorized(session.user, access_type):
                return False
        return True

    @abstractmethod
    async def determine_required_access_types(self, request: MaaSRequest, user) -> tuple:
        """
        Determine what access is required for this request from this user to be accepted.

        Determine the necessary access types for which the given user needs to be authorized in order for the user to
        be allow to submit this request, in the context of the current state of the system.

        Parameters
        ----------
        request
        user

        Returns
        -------
        A tuple of required access types required for authorization for the given request at this time.
        """
        pass

    async def get_authorized_session(self, request: MaaSRequest) -> Tuple[
        Optional[Session], bool, Optional[InitRequestResponseReason], Optional[str]]:
        """
        Get the request's session and whether it is authorized to make such a request.

        Determine the session for this request via a lookup using the request's property for the secret.  Check whether
        the session is authorized to make a request of this nature, with a failed lookup interpreted as not authorized.

        If the session is not authorized to make this request, also get a ::class:`InitRequestResponseReason` and
        message string to appropriately indicating why not.

        Return these four items (session, authorization status, reason, and message), substituting ``None`` for the
        reason and message if the request is authorized.

        Parameters
        ----------
        request : MaaSRequest
            The request for which to get the session and authorization information.

        Returns
        -------
        Tuple[Optional[Session], bool, Optional[InitRequestResponseReason], Optional[str]]
            The retrieved ::class:`Session`, whether the session is authorized for this request, an optional reason for
            indicating when/why the session is not authorized, and an optional message describing when/why the session
            is not authorized.
        """
        session = self._session_manager.lookup_session_by_secret(request.session_secret)
        if session is None:
            is_authorized = False
            reason = InitRequestResponseReason.UNRECOGNIZED_SESSION_SECRET
            msg = 'Request {} does not correspond to a known authenticated session'.format(request.to_json())
        elif not await self._is_authorized(request=request, session=session):
            is_authorized = False
            reason = InitRequestResponseReason.UNAUTHORIZED
            msg = 'User {} in session [{}] not authorized for NWM job request {}'.format(
                session.user, str(session.session_id), request.to_json())
            logging.debug("*************" + msg)
        else:
            is_authorized = True
            # In this case, the reason and message text have to be deferred until the request succeeds or fails
            reason = None
            msg = None
        return session, is_authorized, reason, msg

    @property
    @abstractmethod
    def service_client(self) -> InternalServiceClient:
        """
        Get the client for interacting with the service, which also is a context manager for connections.

        Returns
        -------
        InternalServiceClient
            The client for interacting with the service.
        """
        pass

    @property
    def service_ssl_dir(self) -> Path:
        return self._service_ssl_dir

    @property
    def service_url(self) -> str:
        if self._service_url is None:
            self._service_url = 'wss://{}:{}'.format(str(self._service_host), str(self._service_port))
        return self._service_url


class PartitionRequestHandler(MaaSRequestHandler):

    def __init__(self, session_manager: SessionManager, authorizer: Authorizer, partition_service_host: str,
                 partition_service_port: int, partition_service_ssl_dir: Path):
        super(PartitionRequestHandler, self).__init__(session_manager=session_manager,
                                                      authorizer=authorizer,
                                                      service_host=partition_service_host,
                                                      service_port=partition_service_port,
                                                      service_ssl_dir=partition_service_ssl_dir)

        # TODO: implement properly
        self._default_required_access_type = None

        self._service_client = None

    async def determine_required_access_types(self, request: PartitionRequest, user) -> tuple:
        """
        Determine what access is required for this request from this user to be accepted.

        Determine the necessary access types for which the given user needs to be authorized in order for the user to
        be allow to submit this request, in the context of the current state of the system.

        Parameters
        ----------
        request
        user

        Returns
        -------
        A tuple of required access types required for authorization for the given request at this time.
        """
        # TODO: implement; in particular, consider things like current job count for user, and whether different access
        #   types are required at different counts.
        # FIXME: for now, just use the default type (which happens to be "everything")
        return self._default_required_access_type,

    @property
    def service_client(self) -> PartitionerServiceClient:
        if self._service_client is None:
            self._service_client = PartitionerServiceClient(self.service_url, self.service_ssl_dir)
        return self._service_client

    async def handle_request(self, request: PartitionRequest, **kwargs) -> PartitionResponse:
        session, is_authorized, reason, msg = self.get_authorized_session(request)
        if not is_authorized:
            return PartitionResponse(success=False, reason=reason.name, message=msg)
        # In this case, we actually can pass the request as-is straight through (i.e., after confirming authorization)
        async with self.service_client as client:
            response = await client.async_make_request(request)
            logging.debug("************* {} received response:\n{}".format(self.__class__.__name__, str(response)))
        # Likewise, can just send back the response from the internal service client
        return response