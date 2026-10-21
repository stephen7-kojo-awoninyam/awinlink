from django.urls import path

from . import classroom_api_views as views
from .whiteboard_api import WhiteboardAPIView, ClassroomChatAPIView


urlpatterns = [
    path("classrooms/<int:classroom_id>/users/", views.ClassroomUserSearchAPIView.as_view(), name="classroom_user_search"),
    path("classrooms/<int:classroom_id>/staff/", views.ClassroomStaffAPIView.as_view(), name="classroom_staff"),
    path("sessions/<int:session_id>/chat/", ClassroomChatAPIView.as_view(), name="classroom_chat"),
    path("sessions/<int:session_id>/whiteboard/", WhiteboardAPIView.as_view(), name="classroom_whiteboard"),
    path("classrooms/<int:classroom_id>/invitations/", views.ClassroomInvitationListCreateAPIView.as_view(), name="classroom_invitations"),
    path("classrooms/<int:classroom_id>/invitations/<int:invitation_id>/revoke/", views.ClassroomInvitationRevokeAPIView.as_view(), name="classroom_invitation_revoke"),
    path("classroom-invitations/", views.MyClassroomInvitationsAPIView.as_view(), name="my_classroom_invitations"),
    path("classroom-invitations/<int:invitation_id>/", views.ClassroomInvitationDetailAPIView.as_view(), name="classroom_invitation_detail"),
    path("classroom-invitations/<int:invitation_id>/accept/", views.ClassroomInvitationAcceptAPIView.as_view(), name="classroom_invitation_accept"),
    path("classroom-invitations/<int:invitation_id>/decline/", views.ClassroomInvitationDeclineAPIView.as_view(), name="classroom_invitation_decline"),
    path("classrooms/", views.ClassroomListCreateAPIView.as_view(), name="classroom_list_create"),
    path("classrooms/<int:classroom_id>/", views.ClassroomDetailAPIView.as_view(), name="classroom_detail"),
    path("classrooms/<int:classroom_id>/sessions/", views.ClassroomSessionListScheduleAPIView.as_view(), name="classroom_sessions"),
    path("sessions/<int:session_id>/", views.SessionDetailAPIView.as_view(), name="classroom_session_detail"),
    path("sessions/<int:session_id>/participants/", views.SessionParticipantsAPIView.as_view(), name="classroom_session_participants"),
    path("sessions/<int:session_id>/request-admission/", views.SessionRequestAdmissionAPIView.as_view(), name="classroom_session_request_admission"),
    path("sessions/<int:session_id>/start/", views.SessionStartAPIView.as_view(), name="classroom_session_start"),
    path("sessions/<int:session_id>/join/", views.SessionJoinAPIView.as_view(), name="classroom_session_join"),
    path("sessions/<int:session_id>/leave/", views.SessionLeaveAPIView.as_view(), name="classroom_session_leave"),
    path("sessions/<int:session_id>/participants/<int:participant_id>/admit/", views.SessionAdmitParticipantAPIView.as_view(), name="classroom_session_admit"),
    path("sessions/<int:session_id>/participants/<int:participant_id>/remove/", views.SessionRemoveParticipantAPIView.as_view(), name="classroom_session_remove"),
    path("sessions/<int:session_id>/end/", views.SessionEndAPIView.as_view(), name="classroom_session_end"),
    path("sessions/<int:session_id>/cancel/", views.SessionCancelAPIView.as_view(), name="classroom_session_cancel"),
    path("sessions/<int:session_id>/attendance/", views.SessionAttendanceAPIView.as_view(), name="classroom_session_attendance"),
]
