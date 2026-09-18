from django.db import models
class ProfileStrengthService:


    @staticmethod
    def calculate_strength(talent):

        score = 0



        # -----------------------------
        # Basic Information (30%)
        # -----------------------------


        if talent.profile_photo:

            score += 10



        if talent.headline:

            score += 10



        if talent.biography:

            score += 10




        # -----------------------------
        # Location Information (10%)
        # -----------------------------


        if talent.country:

            score += 5


        if talent.city:

            score += 5




        # -----------------------------
        # Skills and Domains (25%)
        # -----------------------------


        if talent.skills.exists():

            score += 15



        if talent.domains.exists():

            score += 10




        # -----------------------------
        # Portfolio and Achievements (20%)
        # -----------------------------


        if hasattr(talent, "portfolio_items"):

            if talent.portfolio_items.exists():

                score += 10




        if hasattr(talent, "achievements"):

            if talent.achievements.exists():

                score += 10





        # -----------------------------
        # Professional Evidence (10%)
        # -----------------------------


        if hasattr(talent, "certifications"):

            if talent.certifications.exists():

                score += 5



        if hasattr(talent, "experiences"):

            if talent.experiences.exists():

                score += 5





        # -----------------------------
        # Verification (5%)
        # -----------------------------


        if talent.verified:

            score += 5




        return score


# =========================================================
# FOLLOWER ANALYTICS SERVICE
# =========================================================

class FollowerAnalyticsService:


    @staticmethod
    def get_follower_count(talent):

        """
        Return the actual number of users following this talent.
        """

        from connections.models import Follow

        return Follow.objects.filter(
            following=talent.user
        ).count()


    @staticmethod
    def sync_follower_count(talent):

        """
        Calculate the actual follower count and synchronize
        TalentProfile.followers_count with the Follow records.
        """

        follower_count = FollowerAnalyticsService.get_follower_count(
            talent
        )

        if talent.followers_count != follower_count:

            talent.followers_count = follower_count

            talent.save(
                update_fields=["followers_count"]
            )

        return follower_count


    @staticmethod
    def is_verification_eligible(talent):

        """
        Determine whether a talent has reached the
        follower threshold for verification eligibility.

        200,000+ followers = eligible for verification review.
        """

        follower_count = FollowerAnalyticsService.get_follower_count(
            talent
        )

        return follower_count >= 200_000


    @staticmethod
    def is_role_model_eligible(talent):

        """
        Determine whether a talent has reached the
        follower threshold for Role Model eligibility.

        500,000+ followers = eligible for Role Model review.
        """

        follower_count = FollowerAnalyticsService.get_follower_count(
            talent
        )

        return follower_count >= 500_000
    
    
    @staticmethod
    def create_role_model_assignment(talent, assigned_by=None, category="", reason=""):
        """
        Create a pending Role Model assignment for an eligible talent.

        Eligibility is based on the actual follower count and the
        Role Model qualification system.

        Reuses an existing pending/active assignment instead of
        creating duplicates.
        """

        from talents.models import RoleModelAssignment

        eligibility = FollowerAnalyticsService.get_role_model_eligibility(
            talent
        )

        # Talent must be eligible for Role Model review
        if not eligibility["eligible"]:
            return None

        # Do not create duplicate pending or active assignments
        existing_assignment = RoleModelAssignment.objects.filter(
            talent=talent,
            status__in=["PENDING", "ACTIVE"]
        ).first()

        if existing_assignment:
            return existing_assignment

        assignment = RoleModelAssignment.objects.create(
            talent=talent,
            status="PENDING",
            score=eligibility["score"],
            category=category,
            reason=reason,
            assigned_by=assigned_by,
        )

        return assignment
    
    @staticmethod
    def activate_role_model_assignment(assignment, reviewed_by=None):
        """
        Approve a pending Role Model assignment.

        Only ADMIN users can approve a Role Model assignment.
        """

        from django.utils import timezone

        if reviewed_by is None:
            raise ValueError(
                "An admin reviewer is required to activate a Role Model assignment."
            )

        if reviewed_by.role != "ADMIN":
            raise PermissionError(
                "Only ADMIN users can activate Role Model assignments."
            )

        assignment.status = "ACTIVE"
        assignment.reviewed_at = timezone.now()
        assignment.assigned_at = assignment.assigned_at or timezone.now()
        assignment.reviewed_by = reviewed_by

        assignment.save()

        talent = assignment.talent

        talent.is_role_model = True

        if assignment.category:
            talent.role_model_category = assignment.category

        talent.save(
            update_fields=[
                "is_role_model",
                "role_model_category",
            ]
        )

        return assignment
    
    @staticmethod
    def is_active_role_model(talent):
        """
        Return True only when the talent has an ACTIVE
        Role Model assignment.
        """
        from talents.models import RoleModelAssignment

        return RoleModelAssignment.objects.filter(
            talent=talent,
            status="ACTIVE"
        ).exists()
    
    @staticmethod
    def revoke_role_model_assignment(
        assignment,
        reviewed_by=None,
        reason=""
    ):
        """
        Revoke a Role Model assignment.

        Only ADMIN users can revoke a Role Model assignment.
        """

        from django.utils import timezone

        if reviewed_by is None:
            raise ValueError(
                "An admin reviewer is required to revoke a Role Model assignment."
            )

        if reviewed_by.role != "ADMIN":
            raise PermissionError(
                "Only ADMIN users can revoke Role Model assignments."
            )

        assignment.status = "REVOKED"
        assignment.revoked_at = timezone.now()
        assignment.reviewed_at = timezone.now()
        assignment.reviewed_by = reviewed_by

        if reason:
            assignment.reason = reason

        assignment.save()

        talent = assignment.talent

        talent.is_role_model = False

        talent.save(
            update_fields=[
                "is_role_model",
            ]
        )

        return assignment
    
 
    @staticmethod
    def pause_role_model_assignment(
        assignment,
        reviewed_by=None,
        reason=""
    ):
        """
        Temporarily pause an active Role Model assignment.

        Only ADMIN users can pause a Role Model assignment.
        """

        if reviewed_by is None:
            raise ValueError(
                "An admin reviewer is required to pause a Role Model assignment."
            )

        if reviewed_by.role != "ADMIN":
            raise PermissionError(
                "Only ADMIN users can pause Role Model assignments."
            )

        if assignment.status != "ACTIVE":
            return assignment

        assignment.status = "PAUSED"
        assignment.reviewed_by = reviewed_by

        if reason:
            assignment.reason = reason

        assignment.save()

        return assignment
    
    
    @staticmethod
    def resume_role_model_assignment(assignment):
        """
        Resume a paused Role Model assignment.
        """

        if assignment.status != "PAUSED":
            return assignment

        assignment.status = "ACTIVE"
        assignment.save()

        return assignment
    
    
    
    @staticmethod
    def complete_role_model_assignment(
        assignment,
        reviewed_by=None
    ):
        """
        Mark an active Role Model assignment as completed.

        Only ADMIN users can complete a Role Model assignment.
        """

        from django.utils import timezone

        if reviewed_by is None:
            raise ValueError(
                "An admin reviewer is required to complete a Role Model assignment."
            )

        if reviewed_by.role != "ADMIN":
            raise PermissionError(
                "Only ADMIN users can complete Role Model assignments."
            )

        if assignment.status != "ACTIVE":
            return assignment

        assignment.status = "COMPLETED"
        assignment.completed_at = timezone.now()
        assignment.reviewed_by = reviewed_by
        assignment.save()

        talent = assignment.talent

        talent.is_role_model = False

        talent.save(
            update_fields=[
                "is_role_model",
            ]
        )

        return assignment
    
    
    @staticmethod
    def create_manual_role_model_assignment(
        talent,
        assigned_by,
        category="",
        reason=""
    ):
        """
        Manually designate a talent as a Role Model.

        Manual Role Model assignments do not require the
        normal follower-count qualification process.

        Only ADMIN users can create manual assignments.
        """

        from django.utils import timezone
        from talents.models import RoleModelAssignment

        if assigned_by is None:
            raise ValueError(
                "An admin user is required for a manual Role Model assignment."
            )

        if assigned_by.role != "ADMIN":
            raise PermissionError(
                "Only ADMIN users can manually assign Role Models."
            )

        existing_assignment = RoleModelAssignment.objects.filter(
            talent=talent,
            status__in=["PENDING", "ACTIVE", "PAUSED"]
        ).first()

        if existing_assignment:
            return existing_assignment

        assignment = RoleModelAssignment.objects.create(
            talent=talent,
            status="ACTIVE",
            assignment_type="MANUAL",
            score=FollowerAnalyticsService.calculate_role_model_score(
                talent
            ),
            category=category,
            reason=reason,
            assigned_by=assigned_by,
            reviewed_by=assigned_by,
            assigned_at=timezone.now(),
            reviewed_at=timezone.now(),
        )

        talent.is_role_model = True

        if category:
            talent.role_model_category = category

        talent.save(
            update_fields=[
                "is_role_model",
                "role_model_category",
            ]
        )

        return assignment


    @staticmethod
    def has_strong_role_model_threshold(talent):

        """
        Determine whether a talent has reached the stronger
        1,000,000+ follower threshold.
        """

        follower_count = FollowerAnalyticsService.get_follower_count(
            talent
        )

        return follower_count >= 1_000_000
    
    @staticmethod
    def calculate_role_model_score(talent):
        """
        Calculate a Role Model qualification score from 0-100.

        Factors:
            1. Follower reach       - 25 points
            2. Expertise            - 20 points
            3. Credibility          - 15 points
            4. Engagement           - 15 points
            5. Impact / reach       - 10 points
            6. Content activity     - 10 points
            7. Profile quality      - 5 points

        Follower count provides the eligibility threshold,
        but does not automatically make someone a Role Model.
        """

        from feed.models import Post

        score = 0

        # =====================================================
        # 1. FOLLOWER REACH — 25 POINTS
        # =====================================================

        follower_count = (
            FollowerAnalyticsService.get_follower_count(talent)
        )

        if follower_count >= 1_000_000:
            score += 25
        elif follower_count >= 500_000:
            score += 20
        elif follower_count >= 200_000:
            score += 10
        elif follower_count >= 100_000:
            score += 5


        # =====================================================
        # 2. EXPERTISE — 20 POINTS
        # =====================================================

        if talent.domains.exists():
            score += 10

        if talent.skills.exists():
            score += 10


        # =====================================================
        # 3. CREDIBILITY — 15 POINTS
        # =====================================================

        # Verification
        if talent.verified:
            score += 5

        # Achievements
        if talent.achievements.exists():
            score += 4

        # Certifications
        if talent.certifications.exists():
            score += 3

        # Professional experience
        if talent.experiences.exists():
            score += 3


        # =====================================================
        # 4. ENGAGEMENT — 15 POINTS
        # =====================================================

        posts = Post.objects.filter(
            talent=talent
        )

        post_count = posts.count()

        total_likes = (
            Post.objects.filter(
                talent=talent
            ).aggregate(
                total=models.Count("likes")
            )["total"] or 0
        )

        total_comments = (
            Post.objects.filter(
                talent=talent
            ).aggregate(
                total=models.Count("comments")
            )["total"] or 0
        )

        total_shares = (
            Post.objects.filter(
                talent=talent
            ).aggregate(
                total=models.Count("shares")
            )["total"] or 0
        )

        total_saves = (
            Post.objects.filter(
                talent=talent
            ).aggregate(
                total=models.Count("saves")
            )["total"] or 0
        )

        total_engagement = (
            total_likes
            + total_comments
            + total_shares
            + total_saves
        )

        if post_count > 0:

            engagement_per_post = (
                total_engagement / post_count
            )

            if engagement_per_post >= 100:
                score += 15

            elif engagement_per_post >= 50:
                score += 12

            elif engagement_per_post >= 20:
                score += 9

            elif engagement_per_post >= 10:
                score += 6

            elif engagement_per_post > 0:
                score += 3


        # =====================================================
        # 5. IMPACT / REACH — 10 POINTS
        # =====================================================

        total_views = (
            posts.aggregate(
                total=models.Sum("views")
            )["total"] or 0
        )

        if total_views >= 1_000_000:
            score += 10

        elif total_views >= 500_000:
            score += 8

        elif total_views >= 100_000:
            score += 6

        elif total_views >= 10_000:
            score += 4

        elif total_views > 0:
            score += 2


        # =====================================================
        # 6. CONTENT ACTIVITY — 10 POINTS
        # =====================================================

        if post_count >= 100:
            score += 10

        elif post_count >= 50:
            score += 8

        elif post_count >= 20:
            score += 6

        elif post_count >= 10:
            score += 4

        elif post_count >= 5:
            score += 2


        # =====================================================
        # 7. PROFILE QUALITY — 5 POINTS
        # =====================================================

        if talent.headline:
            score += 1

        if talent.biography:
            score += 1

        if talent.country:
            score += 1

        if talent.city:
            score += 1

        if talent.profile_photo:
            score += 1


        # =====================================================
        # FINAL SCORE
        # =====================================================

        return min(score, 100)
    
    
    @staticmethod
    def get_role_model_eligibility(talent):
        """
        Determine the Role Model qualification level.

        500,000+ followers:
            Eligible for Role Model review.

        1,000,000+ followers:
            Strong Role Model qualification.

        Follower count alone does not automatically make
        someone a Role Model.
        """

        follower_count = FollowerAnalyticsService.get_follower_count(
            talent
        )

        score = FollowerAnalyticsService.calculate_role_model_score(
            talent
        )

        if follower_count < 500_000:
            return {
                "eligible": False,
                "level": "NOT_ELIGIBLE",
                "follower_count": follower_count,
                "score": score,
            }

        if follower_count >= 1_000_000:
            return {
                "eligible": True,
                "level": "STRONG",
                "follower_count": follower_count,
                "score": score,
            }

        return {
            "eligible": True,
            "level": "ELIGIBLE",
            "follower_count": follower_count,
            "score": score,
        }
    
    
    @staticmethod
    def create_verification_request_if_eligible(talent):
        """
        Create a verification request when a talent is eligible
        based on the 200,000 follower threshold.

        200,000+ followers means eligible for verification review.
        It does NOT automatically verify the talent.
        """

        from talents.models import VerificationRequest

        # Already verified talents do not need another request
        if talent.verified:
            return None

        # Check the actual follower count
        follower_count = FollowerAnalyticsService.get_follower_count(
            talent
        )

        # Must have at least 200,000 followers
        if follower_count < 200_000:
            return None

        # Do not create duplicate pending requests
        existing_request = VerificationRequest.objects.filter(
            talent=talent,
            status="PENDING"
        ).first()

        if existing_request:
            return existing_request

        # A verification request currently requires a document.
        # We therefore do not create one automatically yet because
        # there is no document supplied by the talent.
        return None
    
    @staticmethod
    def get_verification_status(talent):
        """
        Return the current verification eligibility/status
        for a talent.
        """

        from talents.models import VerificationRequest

        if talent.verified:
            return "VERIFIED"

        follower_count = FollowerAnalyticsService.get_follower_count(
            talent
        )

        if follower_count < 200_000:
            return "NOT_ELIGIBLE"

        pending_request = VerificationRequest.objects.filter(
            talent=talent,
            status="PENDING"
        ).first()

        if pending_request:
            return "PENDING_REVIEW"

        return "ELIGIBLE"

