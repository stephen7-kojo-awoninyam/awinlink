from talents.models import TalentProfile
from talents.services import ProfileStrengthService
from analytics.models import RecommendationHistory
from feed.models import Post
from connections.models import (
    Follow,
    OrganizationFollow,
    Connection,
)

from scouts.models import (
    ScoutProfile,
    ScoutTalentView,
    ScoutTalentFollow,
    ScoutTalentBookmark,
)

from coaches.models import (
    CoachProfile,
    CoachTalentView,
    CoachTalentFollow,
    CoachTalentBookmark,
)

from learning.models import (
    Course,
    Enrollment,
)

from feed.models import (
    Post,
    PostLike,
    Comment,
    SavedPost,
    SharedPost,
)



class RecommendationEngine:


    @staticmethod
    def record_recommendation(
        organization,
        talent,
        opportunity,
        score
    ):
        recommendation, created = (
            RecommendationHistory.objects.update_or_create(
                organization=organization,
                talent=talent,
                opportunity=opportunity,
                defaults={
                    "score": score
                }
            )
        )

        return recommendation



    @staticmethod
    def get_candidates(opportunity):

        talents = TalentProfile.objects.all()

        # =================================
        # DOMAIN FILTER
        # =================================

        if opportunity.domain:

            talents = talents.filter(
                domains=opportunity.domain
            )

        # =================================
        # LOCATION FILTER
        # =================================
        #
        # Opportunity location may be:
        #
        # Accra, Ghana
        #
        # TalentProfile.country may be:
        #
        # Ghana
        #
        # Therefore we extract the country portion.
        #

        if opportunity.location:

            location_parts = [
                part.strip()
                for part in opportunity.location.split(",")
                if part.strip()
            ]

            if location_parts:

                country = location_parts[-1]

                talents = talents.filter(
                    country__icontains=country
                )

        # =================================
        # AVAILABILITY FILTER
        # =================================

        talents = talents.filter(
            availability_status="AVAILABLE"
        )

        return talents.distinct()





    @staticmethod
    def calculate_score(talent, opportunity):


        score = 0



        # =================================
        # DOMAIN MATCH (40)
        # =================================


        if opportunity.domain:


            if talent.domains.filter(

                id=opportunity.domain.id

            ).exists():


                score += 40





        # =================================
        # SKILLS MATCH (30)
        # =================================


        required_skills = opportunity.skills.all()


        if required_skills.exists():


            matched_skills = talent.skills.filter(

                id__in=required_skills.values_list(

                    "id",

                    flat=True

                )

            ).count()



            skill_score = (

                matched_skills /

                required_skills.count()

            ) * 30



            score += skill_score





        # =================================
        # EXPERIENCE (10)
        # =================================


        experience_count = talent.experiences.count()


        score += min(

            experience_count * 2,

            10

        )




        # =================================
        # PORTFOLIO (5)
        # =================================


        if talent.portfolio_items.exists():


            score += 5





        # =================================
        # VERIFICATION (5)
        # =================================


        if talent.verified:


            score += 5





        # =================================
        # PROFILE STRENGTH (5)
        # =================================


        strength = ProfileStrengthService.calculate_strength(

            talent

        )


        score += (

            strength / 100

        ) * 5





        # =================================
        # ACHIEVEMENTS (3)
        # =================================


        achievement_count = talent.achievements.count()


        score += min(

            achievement_count,

            3

        )





        # =================================
        # CERTIFICATIONS (2)
        # =================================


        certificate_count = talent.event_certificates.count()


        score += min(
            certificate_count,
            2
        )




        return round(

            min(score,100),

            2

        )

    @staticmethod
    def score_post_for_user(user, post):
        """
        Calculate how relevant a post is to a specific user.

        Higher score = more relevant.
        """

        score = 0

        # ============================================
        # AUTHOR RELATIONSHIP
        # ============================================

        # User follows the author
        if Follow.objects.filter(
            follower=user,
            following=post.author
        ).exists():
            score += 30

        # Accepted professional connection
        if Connection.objects.filter(
            sender=user,
            receiver=post.author,
            status="ACCEPTED"
        ).exists() or Connection.objects.filter(
            sender=post.author,
            receiver=user,
            status="ACCEPTED"
        ).exists():
            score += 25

        # ============================================
        # ORGANIZATION RELATIONSHIP
        # ============================================

        if post.organization:

            if OrganizationFollow.objects.filter(
                user=user,
                organization=post.organization
            ).exists():
                score += 30

        # ============================================
        # ROLE MODEL
        # ============================================

        if post.talent:

            if post.talent.is_role_model:
                score += 20

        # ============================================
        # TALENT DOMAIN MATCH
        # ============================================

        user_talent = getattr(
            user,
            "talent_profile",
            None
        )

        if user_talent and post.talent:

            user_domains = set(
                user_talent.domains.values_list(
                    "id",
                    flat=True
                )
            )

            post_domains = set(
                post.talent.domains.values_list(
                    "id",
                    flat=True
                )
            )

            if user_domains & post_domains:
                score += 15

        # ============================================
        # SKILL MATCH
        # ============================================

        if user_talent and post.talent:

            user_skills = set(
                user_talent.skills.values_list(
                    "id",
                    flat=True
                )
            )

            post_skills = set(
                post.talent.skills.values_list(
                    "id",
                    flat=True
                )
            )

            matched_skills = user_skills & post_skills

            score += min(
                len(matched_skills) * 3,
                15
            )

        # ============================================
        # PREVIOUS INTERACTION
        # ============================================

        if PostLike.objects.filter(
            user=user,
            post=post
        ).exists():
            score += 10

        if SavedPost.objects.filter(
            user=user,
            post=post
        ).exists():
            score += 15

        if Comment.objects.filter(
            user=user,
            post=post
        ).exists():
            score += 10

        if SharedPost.objects.filter(
            user=user,
            post=post
        ).exists():
            score += 15

        # ============================================
        # POST TYPE
        # ============================================

        if post.post_type == "SHOWCASE":
            score += 5

        elif post.post_type == "ACHIEVEMENT":
            score += 5

        elif post.post_type == "TRAINING":
            score += 4

        elif post.post_type == "NEWS":
            score += 3

        elif post.post_type == "ANNOUNCEMENT":
            score += 2

        # ============================================
        # RECENCY
        # ============================================

        from django.utils import timezone

        age_hours = (
            timezone.now() - post.created_at
        ).total_seconds() / 3600

        if age_hours <= 6:
            score += 15

        elif age_hours <= 24:
            score += 12

        elif age_hours <= 72:
            score += 8

        elif age_hours <= 168:
            score += 4

        # ============================================
        # POPULARITY
        # ============================================

        like_count = post.likes.count()
        comment_count = post.comments.count()
        share_count = post.shares.count()

        score += min(like_count, 5)
        score += min(comment_count * 2, 10)
        score += min(share_count * 2, 10)

        return score



    @staticmethod
    def score_talent_for_user(user, talent):
        """
        Calculate how relevant a talent is to a specific user.

        The scorer adapts to the user's available profile information.

        Supported user contexts:
            - Talent / individual
            - Coach
            - Scout
            - Organization
            - Admin / other users

        A talent can have multiple domains and skills.
        """

        score = 0

        user_talent = getattr(
            user,
            "talent_profile",
            None
        )

        # ============================================
        # COACH-SPECIFIC SCORING
        # ============================================

        coach_profile = getattr(
            user,
            "coach_profile",
            None
        )

        if coach_profile:

            return RecommendationEngine.score_talent_for_coach(
                coach_profile,
                talent
            )


        # ============================================
        # SCOUT-SPECIFIC SCORING
        # ============================================

        scout_profile = getattr(
            user,
            "scout_profile",
            None
        )

        if scout_profile:

            return RecommendationEngine.score_talent_for_scout(
                scout_profile,
                talent
            )

        # ============================================
        # TALENT / INDIVIDUAL DOMAIN MATCH
        # ============================================

        if user_talent:

            user_domains = set(
                user_talent.domains.values_list(
                    "id",
                    flat=True
                )
            )

            talent_domains = set(
                talent.domains.values_list(
                    "id",
                    flat=True
                )
            )

            matched_domains = (
                user_domains &
                talent_domains
            )

            score += min(
                len(matched_domains) * 15,
                30
            )

            # ----------------------------------------
            # DOMAIN-SPECIFIC RELATED SKILLS
            # ----------------------------------------

            related_skill_names = (
                RecommendationEngine
                .get_related_skills_for_domains(
                    user_talent.domains.all()
                )
            )

            related_skill_matches = (
                RecommendationEngine
                .get_matching_skills(
                    talent,
                    related_skill_names
                )
            )

            score += min(
                len(related_skill_matches) * 2,
                10
            )

            # ----------------------------------------
            # EXACT SKILL MATCH
            # ----------------------------------------

            user_skills = set(
                user_talent.skills.values_list(
                    "id",
                    flat=True
                )
            )

            talent_skills = set(
                talent.skills.values_list(
                    "id",
                    flat=True
                )
            )

            matched_skills = (
                user_skills &
                talent_skills
            )

            score += min(
                len(matched_skills) * 5,
                25
            )

        # ============================================
        # ORGANIZATION DOMAIN
        # ============================================

        organization_profile = getattr(
            user,
            "organization_profile",
            None
        )

        if (
            organization_profile
            and organization_profile.domain
        ):

            organization_domain = (
                organization_profile.domain.name
            )

            matching_domains = (
                RecommendationEngine
                .get_matching_domains(
                    talent,
                    organization_domain
                )
            )

            if matching_domains:

                score += 20

                related_skill_names = (
                    RecommendationEngine
                    .get_related_skills_for_domains(
                        matching_domains
                    )
                )

                related_skill_matches = (
                    RecommendationEngine
                    .get_matching_skills(
                        talent,
                        related_skill_names
                    )
                )

                score += min(
                    len(related_skill_matches) * 2,
                    10
                )

        # ============================================
        # FOLLOW RELATIONSHIP
        # ============================================

        if Follow.objects.filter(
            follower=user,
            following=talent.user
        ).exists():

            score += 15

        # ============================================
        # CONNECTION RELATIONSHIP
        # ============================================

        if Connection.objects.filter(
            sender=user,
            receiver=talent.user,
            status="ACCEPTED"
        ).exists() or Connection.objects.filter(
            sender=talent.user,
            receiver=user,
            status="ACCEPTED"
        ).exists():

            score += 15

        # ============================================
        # PREVIOUS INTERACTION
        # ============================================

        if PostLike.objects.filter(
            user=user,
            post__talent=talent
        ).exists():

            score += 5

        if Comment.objects.filter(
            user=user,
            post__talent=talent
        ).exists():

            score += 5

        if SavedPost.objects.filter(
            user=user,
            post__talent=talent
        ).exists():

            score += 10

        if SharedPost.objects.filter(
            user=user,
            post__talent=talent
        ).exists():

            score += 10

        # ============================================
        # ROLE MODEL
        # ============================================

        if talent.is_role_model:
            score += 20

        # ============================================
        # VERIFICATION
        # ============================================

        if talent.verified:
            score += 10

        # ============================================
        # PROFILE STRENGTH
        # ============================================

        strength = ProfileStrengthService.calculate_strength(
            talent
        )

        score += (
            strength / 100
        ) * 10

        # ============================================
        # EXPERIENCE
        # ============================================

        experience_count = talent.experiences.count()

        score += min(
            experience_count * 2,
            10
        )

        return round(
            score,
            2
        )


        # ============================================================
        # TALENT-TO-TALENT DISCOVERY
        # ============================================================

    @staticmethod
    def score_talent_for_discovery(source_talent, candidate):
        """
        Calculate how relevant another talent is for discovery.

        This scorer is specifically for talent-to-talent discovery.

        It focuses on:
            - shared domains
            - exact skill matches
            - related skills
            - genuine cross-category skill relationships
            - location
            - verification
            - Role Model status
            - profile strength
            - experience
        """

        if not source_talent or not candidate:
            return 0

        # --------------------------------------------------------
        # DO NOT RECOMMEND THE TALENT TO THEMSELVES
        # --------------------------------------------------------

        if source_talent.user_id == candidate.user_id:
            return 0

        score = 0

        # --------------------------------------------------------
        # SOURCE PROFILE DATA
        # --------------------------------------------------------

        source_domain_ids = set(
            source_talent.domains.values_list(
                "id",
                flat=True
            )
        )

        candidate_domain_ids = set(
            candidate.domains.values_list(
                "id",
                flat=True
            )
        )

        source_skill_ids = set(
            source_talent.skills.values_list(
                "id",
                flat=True
            )
        )

        candidate_skill_ids = set(
            candidate.skills.values_list(
                "id",
                flat=True
            )
        )

        # --------------------------------------------------------
        # SHARED DOMAINS
        # --------------------------------------------------------

        matched_domain_ids = (
            source_domain_ids &
            candidate_domain_ids
        )

        score += min(
            len(matched_domain_ids) * 15,
            30
        )

        # --------------------------------------------------------
        # EXACT SKILLS
        # --------------------------------------------------------

        matched_skill_ids = (
            source_skill_ids &
            candidate_skill_ids
        )

        score += min(
            len(matched_skill_ids) * 5,
            25
        )

        # --------------------------------------------------------
        # RELATED SKILLS
        # --------------------------------------------------------
        #
        # Use the existing SkillRelationship model.
        #
        # Example:
        #
        # Passing → Decision Making = 1.00
        #
        # The relationship strength contributes to the score.
        #

        related_skill_matches = (
            RecommendationEngine
            .get_related_skill_matches(
                source_talent,
                candidate
            )
        )

        # Do not double-count exact skill matches.
        related_skill_matches = [
            match
            for match in related_skill_matches
            if match["related_skill"].id
            not in matched_skill_ids
        ]

        if related_skill_matches:

            related_score = sum(
                match["strength"] * 5
                for match in related_skill_matches
            )

            score += min(
                related_score,
                15
            )

        # --------------------------------------------------------
        # CROSS-CATEGORY DISCOVERY
        # --------------------------------------------------------
        #
        # A different talent category does NOT automatically
        # receive a bonus.
        #
        # A cross-category relationship must have an actual
        # skill bridge:
        #
        #     exact shared skill
        #     OR
        #     SkillRelationship
        #
        # Shared domains are already handled above and should
        # not create an additional cross-category bonus.
        #

        source_category = getattr(
            source_talent,
            "talent_category",
            None
        )

        candidate_category = getattr(
            candidate,
            "talent_category",
            None
        )

        is_cross_category = (
            source_category
            and candidate_category
            and source_category != candidate_category
        )

        if is_cross_category:

            if matched_skill_ids:
                score += 8

            elif related_skill_matches:
                score += 5

        # --------------------------------------------------------
        # LOCATION
        # --------------------------------------------------------

        if (
            source_talent.country
            and candidate.country
            and source_talent.country.strip().lower()
            == candidate.country.strip().lower()
        ):
            score += 5

        if (
            source_talent.city
            and candidate.city
            and source_talent.city.strip().lower()
            == candidate.city.strip().lower()
        ):
            score += 3

        # --------------------------------------------------------
        # VERIFIED PROFILE
        # --------------------------------------------------------

        if candidate.verified:
            score += 5

        # --------------------------------------------------------
        # ROLE MODEL
        # --------------------------------------------------------

        if candidate.is_role_model:
            score += 8

        # --------------------------------------------------------
        # PROFILE STRENGTH
        # --------------------------------------------------------

        try:
            strength = (
                ProfileStrengthService.calculate_strength(
                    candidate
                )
            )

            if isinstance(strength, dict):
                strength = strength.get(
                    "score",
                    0
                )

            score += (
                float(strength) / 100
            ) * 5

        except Exception:
            pass

        # --------------------------------------------------------
        # EXPERIENCE
        # --------------------------------------------------------

        experience_count = (
            candidate.experiences.count()
        )

        score += min(
            experience_count * 1.5,
            6
        )

        return round(
            min(score, 100),
            2
        )


    @staticmethod
    def explain_talent_match(source_talent, candidate):
        """
        Explain why one talent was recommended to another talent.

        Returns a list of human-readable reasons.
        """

        if not source_talent or not candidate:
            return []

        reasons = []

        # --------------------------------------------------------
        # SHARED DOMAINS
        # --------------------------------------------------------

        source_domain_ids = set(
            source_talent.domains.values_list(
                "id",
                flat=True
            )
        )

        candidate_domain_ids = set(
            candidate.domains.values_list(
                "id",
                flat=True
            )
        )

        matched_domain_ids = (
            source_domain_ids &
            candidate_domain_ids
        )

        if matched_domain_ids:

            matched_domains = list(
                source_talent.domains.filter(
                    id__in=matched_domain_ids
                ).values_list(
                    "name",
                    flat=True
                )
            )

            matched_domains = [
                name.strip()
                for name in matched_domains
                if name and name.strip()
            ]

            if matched_domains:

                reasons.append(
                    "You share "
                    + ", ".join(matched_domains[:3])
                    + " domain"
                    + (
                        "s"
                        if len(matched_domains) > 1
                        else ""
                    )
                )

        # --------------------------------------------------------
        # EXACT SKILLS
        # --------------------------------------------------------

        source_skill_ids = set(
            source_talent.skills.values_list(
                "id",
                flat=True
            )
        )

        candidate_skill_ids = set(
            candidate.skills.values_list(
                "id",
                flat=True
            )
        )

        matched_skill_ids = (
            source_skill_ids &
            candidate_skill_ids
        )

        if matched_skill_ids:

            matched_skills = list(
                source_talent.skills.filter(
                    id__in=matched_skill_ids
                ).values_list(
                    "name",
                    flat=True
                )
            )

            matched_skills = [
                name.strip()
                for name in matched_skills
                if name and name.strip()
            ]

            if matched_skills:

                reasons.append(
                    "You share skills such as "
                    + ", ".join(
                        matched_skills[:4]
                    )
                )

        # --------------------------------------------------------
        # RELATED SKILLS
        # --------------------------------------------------------

        related_skill_names = set()

        if source_talent.domains.exists():

            related_skill_names = (
                RecommendationEngine
                .get_related_skills_for_domains(
                    source_talent.domains.all()
                )
            )

        related_skills = (
            RecommendationEngine
            .get_matching_skills(
                candidate,
                related_skill_names
            )
        )

        related_skills = [
            skill
            for skill in related_skills
            if skill.id not in matched_skill_ids
        ]

        if related_skills:

            reasons.append(
                "Has skills related to your interests, "
                + ", ".join(
                    skill.name
                    for skill in related_skills[:3]
                )
            )

        # --------------------------------------------------------
        # CROSS-CATEGORY DISCOVERY
        # --------------------------------------------------------

        source_category = getattr(
            source_talent,
            "talent_category",
            None
        )

        candidate_category = getattr(
            candidate,
            "talent_category",
            None
        )

        if (
            source_category
            and candidate_category
            and source_category != candidate_category
            and (
                matched_domain_ids
                or matched_skill_ids
                or related_skills
            )
        ):

            reasons.append(
                "Explore talent from another category"
            )

        # --------------------------------------------------------
        # LOCATION
        # --------------------------------------------------------

        if (
            source_talent.country
            and candidate.country
            and source_talent.country.strip().lower()
            == candidate.country.strip().lower()
        ):

            reasons.append(
                "You are in the same country"
            )

        if (
            source_talent.city
            and candidate.city
            and source_talent.city.strip().lower()
            == candidate.city.strip().lower()
        ):

            reasons.append(
                "You are in the same city"
            )

        # --------------------------------------------------------
        # QUALITY SIGNALS
        # --------------------------------------------------------

        if candidate.verified:
            reasons.append(
                "Verified talent profile"
            )

        if candidate.is_role_model:
            reasons.append(
                "Recognized as a Role Model"
            )

        # --------------------------------------------------------
        # FALLBACK
        # --------------------------------------------------------

        if not reasons:

            reasons.append(
                "Recommended based on your talent profile"
            )

        return reasons


    @staticmethod
    def recommend_talents_for_talent(
        talent,
        limit=12
    ):
        """
        Recommend other talents for a talent's
        Discover Talents experience.

        Existing follows and accepted connections are excluded
        from the primary discovery feed.

        The result contains:

            {
                "talent": candidate,
                "score": score,
                "reasons": [...]
            }
        """

        if not talent:
            return []

        # --------------------------------------------------------
        # ALL OTHER TALENTS
        # --------------------------------------------------------

        candidates = (
            TalentProfile.objects
            .select_related("user")
            .prefetch_related(
                "domains",
                "skills",
                "experiences"
            )
            .exclude(
                user_id=talent.user_id
            )
        )

        # --------------------------------------------------------
        # EXISTING FOLLOWS
        # --------------------------------------------------------

        followed_user_ids = set(
            Follow.objects.filter(
                follower=talent.user
            ).values_list(
                "following_id",
                flat=True
            )
        )

        # --------------------------------------------------------
        # EXISTING CONNECTIONS
        # --------------------------------------------------------

        sent_connection_ids = set(
            Connection.objects.filter(
                sender=talent.user,
                status="ACCEPTED"
            ).values_list(
                "receiver_id",
                flat=True
            )
        )

        received_connection_ids = set(
            Connection.objects.filter(
                receiver=talent.user,
                status="ACCEPTED"
            ).values_list(
                "sender_id",
                flat=True
            )
        )

        connected_user_ids = (
            sent_connection_ids |
            received_connection_ids
        )

        # --------------------------------------------------------
        # EXCLUDE ALREADY KNOWN PEOPLE
        # --------------------------------------------------------

        excluded_user_ids = (
            followed_user_ids |
            connected_user_ids |
            {talent.user_id}
        )

        candidates = candidates.exclude(
            user_id__in=excluded_user_ids
        )

        # --------------------------------------------------------
        # SCORE CANDIDATES
        # --------------------------------------------------------

        recommendations = []

        for candidate in candidates:

            score = (
                RecommendationEngine
                .score_talent_for_discovery(
                    talent,
                    candidate
                )
            )

            # --------------------------------------------------------
            # MEANINGFUL DISCOVERY RELEVANCE
            # --------------------------------------------------------

            # Shared domain
            has_domain_match = talent.domains.filter(
                id__in=candidate.domains.values_list(
                    "id",
                    flat=True
                )
            ).exists()

            # Exact skill match
            source_skill_ids = set(
                talent.skills.values_list(
                    "id",
                    flat=True
                )
            )

            candidate_skill_ids = set(
                candidate.skills.values_list(
                    "id",
                    flat=True
                )
            )

            has_skill_match = bool(
                source_skill_ids &
                candidate_skill_ids
            )

            # Related skill match
            related_skill_names = (
                RecommendationEngine
                .get_related_skills_for_domains(
                    talent.domains.all()
                )
            )

            related_skills = (
                RecommendationEngine
                .get_matching_skills(
                    candidate,
                    related_skill_names
                )
            )

            has_related_skill = bool(
                related_skills
            )

            # --------------------------------------------------------
            # EXCLUDE WEAK DISCOVERY MATCHES
            # --------------------------------------------------------

            if not (
                has_domain_match
                or has_skill_match
                or has_related_skill
            ):
                continue

            # Score must still be positive.
            if score <= 0:
                continue

            reasons = (
                RecommendationEngine
                .explain_talent_match(
                    talent,
                    candidate
                )
            )

            # Determine whether this is a cross-category
            # recommendation.
            # --------------------------------------------------------
            # DISCOVERY TYPE
            # --------------------------------------------------------

            source_category = getattr(
                talent,
                "talent_category",
                None
            )

            candidate_category = getattr(
                candidate,
                "talent_category",
                None
            )

            # Shared domain
            has_domain_match = talent.domains.filter(
                id__in=candidate.domains.values_list(
                    "id",
                    flat=True
                )
            ).exists()

            # Exact skill relationship
            source_skill_ids = set(
                talent.skills.values_list(
                    "id",
                    flat=True
                )
            )

            candidate_skill_ids = set(
                candidate.skills.values_list(
                    "id",
                    flat=True
                )
            )

            has_skill_match = bool(
                source_skill_ids &
                candidate_skill_ids
            )

            # Related skill relationship
            related_skill_names = (
                RecommendationEngine
                .get_related_skills_for_domains(
                    talent.domains.all()
                )
            )

            related_skills = (
                RecommendationEngine
                .get_matching_skills(
                    candidate,
                    related_skill_names
                )
            )

            has_related_skill = bool(
                related_skills
            )

            # --------------------------------------------------------
            # CLASSIFY DISCOVERY
            # --------------------------------------------------------

            if (
                source_category
                and candidate_category
                and source_category != candidate_category
                and (
                    has_domain_match
                    or has_skill_match
                    or has_related_skill
                )
            ):
                discovery_type = "CROSS_CATEGORY"

            elif has_domain_match or has_skill_match:
                discovery_type = "SIMILAR"

            elif has_related_skill:
                discovery_type = "RELATED"

            else:
                discovery_type = "RELATED"

            recommendations.append({
                "talent": candidate,
                "score": score,
                "reasons": reasons,
                "discovery_type": discovery_type,
            })

        # --------------------------------------------------------
        # SORT
        # --------------------------------------------------------

        recommendations.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return recommendations[:limit]


    @staticmethod
    def recommend_feed_users(
        user,
        limit=12
    ):
        """
        Recommend users whose talent profiles have meaningful
        relevance to the current user's talent profile.

        This is used by the Feed to discover public content
        from people with meaningful common interests.

        The actual matching logic is delegated to the existing
        talent-to-talent discovery engine.
        """

        if not user:
            return []

        user_talent = getattr(
            user,
            "talent_profile",
            None
        )

        if not user_talent:
            return []

        recommendations = (
            RecommendationEngine
            .recommend_talents_for_talent(
                user_talent,
                limit=limit
            )
        )

        return [
            {
                "user": item["talent"].user,
                "talent": item["talent"],
                "score": item["score"],
                "reasons": item["reasons"],
                "discovery_type": item["discovery_type"],
            }
            for item in recommendations
        ]


    @staticmethod
    def score_talent_for_discovery(
        source_talent,
        candidate
    ):
        """
        Score how relevant one talent is to another
        for the Discover Talents experience.

        Maximum score: 100

        Scoring:
            Shared domains       = 25
            Exact skills         = 25
            Related skills       = 15
            Same talent category = 10
            Experience           = 5
            Achievements         = 5
            Certifications       = 5
            Profile strength     = 5
            Same country         = 3
            Same city            = 2
        """

        if not source_talent or not candidate:
            return 0

        # --------------------------------------------------------
        # DO NOT RECOMMEND SELF
        # --------------------------------------------------------

        if source_talent.user_id == candidate.user_id:
            return 0

        score = 0

        # --------------------------------------------------------
        # SHARED DOMAINS — 25 POINTS
        # --------------------------------------------------------

        source_domain_ids = set(
            source_talent.domains.values_list(
                "id",
                flat=True
            )
        )

        candidate_domain_ids = set(
            candidate.domains.values_list(
                "id",
                flat=True
            )
        )

        matched_domain_ids = (
            source_domain_ids &
            candidate_domain_ids
        )

        if matched_domain_ids:
            score += min(
                len(matched_domain_ids) * 12.5,
                25
            )

        # --------------------------------------------------------
        # EXACT SKILLS — 25 POINTS
        # --------------------------------------------------------

        source_skill_ids = set(
            source_talent.skills.values_list(
                "id",
                flat=True
            )
        )

        candidate_skill_ids = set(
            candidate.skills.values_list(
                "id",
                flat=True
            )
        )

        matched_skill_ids = (
            source_skill_ids &
            candidate_skill_ids
        )

        if matched_skill_ids:
            score += min(
                len(matched_skill_ids) * 5,
                25
            )

        # --------------------------------------------------------
        # RELATED SKILLS — 15 POINTS
        # --------------------------------------------------------

        related_skill_names = set()

        if source_domain_ids:

            related_skill_names = (
                RecommendationEngine
                .get_related_skills_for_domains(
                    source_talent.domains.all()
                )
            )

        related_skills = (
            RecommendationEngine
            .get_matching_skills(
                candidate,
                related_skill_names
            )
        )

        # Remove exact matches so they are not counted twice.
        related_skills = [
            skill
            for skill in related_skills
            if skill.id not in matched_skill_ids
        ]

        if related_skills:
            score += min(
                len(related_skills) * 5,
                15
            )

        # --------------------------------------------------------
        # TALENT CATEGORY — 10 POINTS
        # --------------------------------------------------------

        source_category = getattr(
            source_talent,
            "talent_category",
            None
        )

        candidate_category = getattr(
            candidate,
            "talent_category",
            None
        )

        if (
            source_category
            and candidate_category
            and source_category == candidate_category
        ):
            score += 10

        # IMPORTANT:
        # Different categories are NOT penalized.
        #
        # Awinlink supports cross-category discovery.
        # A technology talent can discover an arts talent,
        # for example, if their skills/domains are relevant.

        # --------------------------------------------------------
        # EXPERIENCE — 5 POINTS
        # --------------------------------------------------------

        experience_count = candidate.experiences.count()

        score += min(
            experience_count,
            5
        )

        # --------------------------------------------------------
        # ACHIEVEMENTS — 5 POINTS
        # --------------------------------------------------------

        achievements_manager = getattr(
            candidate,
            "achievements",
            None
        )

        if achievements_manager:
            achievement_count = achievements_manager.count()

            score += min(
                achievement_count,
                5
            )

        # --------------------------------------------------------
        # CERTIFICATIONS — 5 POINTS
        # --------------------------------------------------------

        certificates_manager = getattr(
            candidate,
            "certificates",
            None
        )

        if certificates_manager:
            certificate_count = certificates_manager.count()

            score += min(
                certificate_count,
                5
            )

        # --------------------------------------------------------
        # PROFILE STRENGTH — 5 POINTS
        # --------------------------------------------------------

        try:
            profile_strength = (
                ProfileStrengthService
                .calculate_strength(candidate)
            )

            if isinstance(profile_strength, dict):
                strength_value = profile_strength.get(
                    "score",
                    0
                )
            else:
                strength_value = profile_strength

            score += min(
                float(strength_value) / 20,
                5
            )

        except Exception:
            pass

        # --------------------------------------------------------
        # SAME COUNTRY — 3 POINTS
        # --------------------------------------------------------

        if (
            source_talent.country
            and candidate.country
            and source_talent.country.strip().lower()
            == candidate.country.strip().lower()
        ):
            score += 3

        # --------------------------------------------------------
        # SAME CITY — 2 POINTS
        # --------------------------------------------------------

        if (
            source_talent.city
            and candidate.city
            and source_talent.city.strip().lower()
            == candidate.city.strip().lower()
        ):
            score += 2

        # --------------------------------------------------------
        # FINAL SCORE
        # --------------------------------------------------------

        return round(
            min(score, 100),
            2
        )

    @staticmethod
    def score_role_model_for_talent(talent, role_model):
        """
        Calculate how relevant a role model is to a specific talent.

        A role model can be relevant through:
            - matching domains
            - related skills
            - exact skills
            - experience
            - achievements
            - certifications
            - verification
            - profile strength
            - location

        A talent may have multiple domains and skills.
        A role model does not need to match every domain.
        Each relevant match contributes to the score.
        """

        score = 0

        # ============================================
        # ROLE MODEL ELIGIBILITY
        # ============================================

        if not role_model.is_role_model:
            return 0

        # Do not recommend the talent themselves
        if role_model.user_id == talent.user_id:
            return 0

        # ============================================
        # DOMAIN MATCH
        # ============================================

        talent_domains = set(
            talent.domains.values_list(
                "id",
                flat=True
            )
        )

        role_model_domains = set(
            role_model.domains.values_list(
                "id",
                flat=True
            )
        )

        matched_domains = (
            talent_domains &
            role_model_domains
        )

        # First matching domain
        if matched_domains:

            score += 25

            # Additional matching domains
            score += min(
                (len(matched_domains) - 1) * 10,
                20
            )

        # ============================================
        # RELATED SKILLS
        # ============================================

        related_skill_matches = []

        if matched_domains:
            matching_domain_objects = role_model.domains.filter(
                id__in=matched_domains
            )

            related_skill_names = (
                RecommendationEngine
                .get_related_skills_for_domains(
                    matching_domain_objects
                )
            )

            related_skill_matches = (
                RecommendationEngine
                .get_matching_skills(
                    talent,
                    related_skill_names
                )
            )

            score += min(
                len(related_skill_matches) * 3,
                15
            )



        # ============================================
        # EXACT SKILL MATCH
        # ============================================

        talent_skill_ids = set(
            talent.skills.values_list(
                "id",
                flat=True
            )
        )

        role_model_skill_ids = set(
            role_model.skills.values_list(
                "id",
                flat=True
            )
        )

        matched_skills = (
            talent_skill_ids &
            role_model_skill_ids
        )

        score += min(
            len(matched_skills) * 5,
            20
        )

        # ============================================
        # RELEVANCE GATE
        # ============================================

        if (
            not matched_domains
            and not matched_skills
            and not related_skill_matches
        ):
            return 0

        # ============================================
        # ROLE MODEL QUALITY
        # ============================================

        if role_model.verified:
            score += 10

        # ============================================
        # EXPERIENCE
        # ============================================

        experience_count = role_model.experiences.count()

        score += min(
            experience_count * 2,
            10
        )

        # ============================================
        # ACHIEVEMENTS
        # ============================================

        achievement_count = role_model.achievements.count()

        score += min(
            achievement_count * 2,
            10
        )

        # ============================================
        # CERTIFICATIONS
        # ============================================

        certification_count = role_model.certifications.count()

        score += min(
            certification_count * 2,
            10
        )

        # ============================================
        # PROFILE STRENGTH
        # ============================================

        strength = ProfileStrengthService.calculate_strength(
            role_model
        )

        score += (
            strength / 100
        ) * 10

        # ============================================
        # LOCATION RELEVANCE
        # ============================================

        if (
            talent.country
            and role_model.country
            and talent.country.strip().lower()
            == role_model.country.strip().lower()
        ):
            score += 5

        if (
            talent.city
            and role_model.city
            and talent.city.strip().lower()
            == role_model.city.strip().lower()
        ):
            score += 3

        return round(
            score,
            2
        )
    @staticmethod
    def recommend_role_models_for_talent(talent, limit=10):
        """
        Recommend the most relevant role models for a talent.

        A talent may have multiple domains and skills.
        Therefore, we do NOT filter role models by a single domain
        before scoring them.

        The scorer determines how relevant each role model is.
        """

        # ============================================
        # FIND ELIGIBLE ROLE MODELS
        # ============================================

        role_models = TalentProfile.objects.filter(
            is_role_model=True
        ).exclude(
            user_id=talent.user_id
        )

        # ============================================
        # EXCLUDE PEOPLE ALREADY FOLLOWED
        # ============================================

        followed_user_ids = set(
            Follow.objects.filter(
                follower=talent.user
            ).values_list(
                "following_id",
                flat=True
            )
        )

        role_models = role_models.exclude(
            user_id__in=followed_user_ids
        )

        # ============================================
        # SCORE ROLE MODELS
        # ============================================

        recommendations = []

        for role_model in role_models:

            score = (
                RecommendationEngine
                .score_role_model_for_talent(
                    talent,
                    role_model
                )
            )

            reasons = (
                RecommendationEngine
                .explain_role_model_match(
                    talent,
                    role_model
                )
            )

            if score <= 0:
               continue

            recommendations.append({
                "role_model": role_model,
                "score": score,
                "reasons": reasons,
            })

        # ============================================
        # RANK BY RELEVANCE
        # ============================================

        recommendations.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        # ============================================
        # RETURN TOP RESULTS
        # ============================================

        return recommendations[:limit]



    @staticmethod
    def explain_role_model_match(talent, role_model):
        """
        Explain why a role model is relevant to a specific talent.

        The explanation considers:

            - shared domains
            - shared skills
            - directly related skills
            - verification
            - experience
            - achievements
            - certifications
            - location

        Direct skill relationships come from SkillRelationship.
        """

        reasons = []

        # ============================================
        # DOMAIN MATCH
        # ============================================

        talent_domains = set(
            talent.domains.values_list(
                "id",
                flat=True
            )
        )

        role_model_domains = set(
            role_model.domains.values_list(
                "id",
                flat=True
            )
        )

        matched_domain_ids = (
            talent_domains &
            role_model_domains
        )

        matched_domain_names = []
        specific_domain_names = []

        if matched_domain_ids:

            matched_domain_names = list(
                talent.domains.filter(
                    id__in=matched_domain_ids
                ).values_list(
                    "name",
                    flat=True
                )
            )

            matched_domain_names = [
                name.strip()
                for name in matched_domain_names
                if name and name.strip()
            ]

            # Prefer the most specific shared domain.
            for domain_name in matched_domain_names:

                domain_lower = domain_name.lower()

                is_parent_domain = False

                for other_domain in matched_domain_names:

                    other_lower = other_domain.lower()

                    if (
                        domain_lower != other_lower
                        and domain_lower in other_lower
                    ):
                        is_parent_domain = True
                        break

                if not is_parent_domain:

                    specific_domain_names.append(
                        domain_name
                    )

            if not specific_domain_names:

                specific_domain_names = (
                    matched_domain_names
                )

            reasons.append(
                "You share the "
                + ", ".join(
                    specific_domain_names
                )
                + " domain"
            )

        # ============================================
        # EXACT SKILL MATCH
        # ============================================

        talent_skill_ids = set(
            talent.skills.values_list(
                "id",
                flat=True
            )
        )

        role_model_skill_ids = set(
            role_model.skills.values_list(
                "id",
                flat=True
            )
        )

        matched_skill_ids = (
            talent_skill_ids &
            role_model_skill_ids
        )

        matched_skills = []

        if matched_skill_ids:

            matched_skills = list(
                talent.skills.filter(
                    id__in=matched_skill_ids
                ).values_list(
                    "name",
                    flat=True
                )
            )

            if matched_skills:

                reasons.append(
                    "You share skills such as "
                    + ", ".join(
                        matched_skills[:5]
                    )
                )

        # ============================================
        # DIRECTLY RELATED SKILLS
        # ============================================

        related_skill_matches = (
            RecommendationEngine
            .get_related_skill_matches_for_role_model(
                talent,
                role_model
            )
        )

        # Remove relationships where both skills are
        # already exact shared skills.
        related_skill_matches = [
            match
            for match in related_skill_matches
            if not (
                match["talent_skill"].id in matched_skill_ids
                and
                match["role_model_skill"].id in matched_skill_ids
            )
        ]

        if related_skill_matches:

            for match in related_skill_matches[:5]:

                talent_skill_name = (
                    match["talent_skill"].name
                )

                role_model_skill_name = (
                    match["role_model_skill"].name
                )

                reasons.append(
                    f"Your {talent_skill_name} is related "
                    f"to this role model's "
                    f"{role_model_skill_name}"
                )

        # ============================================
        # VERIFICATION
        # ============================================

        if role_model.verified:

            reasons.append(
                "This role model has a verified profile"
            )

        # ============================================
        # EXPERIENCE
        # ============================================

        if role_model.experiences.exists():

            reasons.append(
                "This role model has relevant "
                "professional experience"
            )

        # ============================================
        # ACHIEVEMENTS
        # ============================================

        if role_model.achievements.exists():

            reasons.append(
                "This role model has notable achievements"
            )

        # ============================================
        # CERTIFICATIONS
        # ============================================

        if role_model.certifications.exists():

            reasons.append(
                "This role model has professional certifications"
            )

        # ============================================
        # LOCATION
        # ============================================

        if (
            talent.country
            and role_model.country
            and talent.country.strip().lower()
            == role_model.country.strip().lower()
        ):

            reasons.append(
                "This role model is in the same country"
            )

        if (
            talent.city
            and role_model.city
            and talent.city.strip().lower()
            == role_model.city.strip().lower()
        ):

            reasons.append(
                "This role model is in the same city"
            )

        # ============================================
        # FALLBACK
        # ============================================

        if not reasons:

            reasons.append(
                "Recommended based on your profile"
            )

        return reasons

    @staticmethod
    def score_organization_for_user(user, organization):
        """
        Calculate how relevant an organization is to a user.
        """

        score = 0

        # ============================================
        # USER'S TALENT PROFILE
        # ============================================

        user_talent = getattr(
            user,
            "talent_profile",
            None
        )

        # ============================================
        # DOMAIN MATCH
        # ============================================

        if user_talent and organization.domain:

            if user_talent.domains.filter(
                name=organization.domain.name
            ).exists():
                score += 30

        # ============================================
        # CATEGORY MATCH
        # ============================================

        if user_talent and organization.category:

            # Talent category → organization category
            category_map = {
                "SPORTS": "Sports",
                "SCIENCE_TECHNOLOGY": "Technology",
                "ARTS": "Arts",
            }

            talent_category = category_map.get(
                user_talent.talent_category
            )

            if talent_category:

                if organization.category.name.lower() == (
                    talent_category.lower()
                ):
                    score += 20

        # ============================================
        # LOCATION MATCH
        # ============================================

        if user_talent:

            if (
                user_talent.country
                and organization.country
                and user_talent.country.lower()
                == organization.country.lower()
            ):
                score += 10

            if (
                user_talent.city
                and organization.city
                and user_talent.city.lower()
                == organization.city.lower()
            ):
                score += 5

        # ============================================
        # VERIFICATION
        # ============================================

        if organization.verified:
            score += 10

        # ============================================
        # OFFICIAL ORGANIZATION
        # ============================================

        if organization.official:
            score += 5

        # ============================================
        # ORGANIZATION ACTIVITY
        # ============================================

        opportunity_count = organization.opportunities.count()

        score += min(
            opportunity_count * 2,
            10
        )

        # ============================================
        # ORGANIZATION FOLLOWERS
        # ============================================

        follower_count = organization.followers.count()

        score += min(
            follower_count,
            5
        )

        return round(
            score,
            2
        )

    @staticmethod
    def score_opportunity_for_user(user, opportunity):
        """
        Calculate how relevant an opportunity is to a user.
        """

        talent = getattr(
            user,
            "talent_profile",
            None
        )

        if not talent:
            return 0

        # Use the existing talent-opportunity
        # matching engine as the foundation.
        score = RecommendationEngine.calculate_score(
            talent,
            opportunity
        )

        # ============================================
        # ORGANIZATION RELATIONSHIP
        # ============================================

        if opportunity.organization:

            if OrganizationFollow.objects.filter(
                user=user,
                organization=opportunity.organization
            ).exists():
                score += 10

        # ============================================
        # LOCATION RELEVANCE
        # ============================================

        if (
            talent.country
            and opportunity.location
            and talent.country.lower()
            in opportunity.location.lower()
        ):
            score += 5

        # ============================================
        # AVAILABILITY
        # ============================================

        if talent.availability_status == "AVAILABLE":
            score += 5

        # ============================================
        # ACTIVE OPPORTUNITY
        # ============================================

        if opportunity.active:
            score += 5

        return round(
            min(score, 100),
            2
        )


    def score_course_for_talent(self, talent, course):
        """
        Score how relevant a learning course is to a talent.

        The recommendation is based on:
            - course category/domain relevance
            - talent skills
            - related skills
            - talent experience
            - achievements
            - certifications
            - profile strength
            - course level
            - creator relationship
            - course quality
            - free-course preference
        """

        if not talent or not course:
            return 0

        score = 0

        user = talent.user

        # =====================================================
        # BASIC ELIGIBILITY
        # =====================================================

        if course.status != "APPROVED":
            return 0

        # Do not recommend the talent's own course
        if course.creator_id == user.id:
            return 0

        # =====================================================
        # COURSE CATEGORY MATCH
        # =====================================================

        category_name = self.normalize_text(
            course.category.name
        )

        talent_domains = list(
            talent.domains.all()
        )

        domain_match = False

        for domain in talent_domains:

            domain_name = self.normalize_text(
                domain.name
            )

            if (
                domain_name in category_name
                or category_name in domain_name
            ):
                domain_match = True
                break

        if domain_match:
            score += 30

        # =====================================================
        # SKILL MATCH
        # =====================================================

        talent_skills = list(
            talent.skills.all()
        )

        course_text = self.normalize_text(
            f"{course.title} {course.description}"
        )

        exact_skill_matches = 0
        related_skill_matches = 0

        for skill in talent_skills:

            skill_name = self.normalize_text(
                skill.name
            )

            if not skill_name:
                continue

            if skill_name in course_text:
                exact_skill_matches += 1

        score += min(
            exact_skill_matches * 10,
            25
        )

        # =====================================================
        # RELATED SKILLS
        # =====================================================

        for domain in talent_domains:

            related_skills = self.get_related_skills_for_domains(
                [domain]
            )

            for related_skill in related_skills:

                related_name = self.normalize_text(
                    related_skill
                )

                if (
                    related_name
                    and related_name in course_text
                ):
                    related_skill_matches += 1

        score += min(
            related_skill_matches * 5,
            15
        )

        # =====================================================
        # EXPERIENCE
        # =====================================================

        experience_count = talent.experiences.count()

        if experience_count >= 3:
            score += 8

        elif experience_count >= 1:
            score += 5

        # =====================================================
        # ACHIEVEMENTS
        # =====================================================

        achievement_count = talent.achievements.count()

        if achievement_count >= 3:
            score += 5

        elif achievement_count >= 1:
            score += 3

        # =====================================================
        # CERTIFICATIONS
        # =====================================================

        certification_count = talent.certifications.count()

        if certification_count >= 2:
            score += 4

        elif certification_count >= 1:
            score += 2

        # =====================================================
        # PROFILE STRENGTH
        # =====================================================

        # =====================================================
        # PROFILE STRENGTH
        # =====================================================

        profile_strength = (
            ProfileStrengthService.calculate_strength(
                talent
            )
        )

        if profile_strength >= 80:
            score += 5

        elif profile_strength >= 50:
            score += 3

        # =====================================================
        # COURSE LEVEL
        # =====================================================

        if course.level == "BEGINNER":

            score += 3

        elif course.level == "INTERMEDIATE":

            if experience_count >= 1:
                score += 5
            else:
                score += 2

        elif course.level == "ADVANCED":

            if (
                experience_count >= 2
                or certification_count >= 1
            ):
                score += 5
            else:
                score += 1

        # =====================================================
        # COURSE QUALITY
        # =====================================================

        review_count = course.reviews.count()

        if review_count >= 10:
            score += 5

        elif review_count >= 5:
            score += 3

        elif review_count >= 1:
            score += 1

        # =====================================================
        # FREE COURSE
        # =====================================================

        if course.is_free:
            score += 2

        # =====================================================
        # FINAL CAP
        # =====================================================

        return min(score, 100)


    def get_course_recommendation_reason(self, talent, course):
        """
        Explain why a course is recommended to a talent.
        """

        reasons = []

        # =====================================================
        # DOMAIN / CATEGORY MATCH
        # =====================================================

        category_name = self.normalize_text(
            course.category.name
        )

        for domain in talent.domains.all():

            domain_name = self.normalize_text(
                domain.name
            )

            if (
                domain_name in category_name
                or category_name in domain_name
            ):
                reasons.append(
                    f"Matches your {domain.name} domain."
                )
                break

        # =====================================================
        # SKILL MATCH
        # =====================================================

        course_text = self.normalize_text(
            f"{course.title} {course.description}"
        )

        matched_skills = []

        for skill in talent.skills.all():

            skill_name = self.normalize_text(
                skill.name
            )

            if skill_name and skill_name in course_text:
                matched_skills.append(skill.name)

        if matched_skills:

            if len(matched_skills) == 1:
                reasons.append(
                    f"Matches your {matched_skills[0]} skill."
                )

            else:
                displayed_skills = matched_skills[:3]

                reasons.append(
                    "Matches your skills in "
                    + ", ".join(displayed_skills)
                    + "."
                )

        # =====================================================
        # LEVEL
        # =====================================================

        if course.level == "BEGINNER":
            reasons.append(
                "Suitable for beginner-level learning."
            )

        elif course.level == "INTERMEDIATE":
            reasons.append(
                "Suitable for intermediate-level learning."
            )

        elif course.level == "ADVANCED":
            reasons.append(
                "Suitable for advanced-level learning."
            )

        # =====================================================
        # FREE COURSE
        # =====================================================

        if course.is_free:
            reasons.append(
                "This course is free."
            )

        # =====================================================
        # FALLBACK
        # =====================================================

        if not reasons:
            reasons.append(
                "Recommended based on your profile."
            )

        return " ".join(reasons)

    def recommend_courses_for_talent(self, talent, limit=10):
        """
        Return the most relevant approved learning courses
        for a talent, including recommendation reasons.
        """

        if not talent:
            return []

        from learning.models import Course

        courses = Course.objects.filter(
            status="APPROVED"
        ).exclude(
            creator_id=talent.user_id
        )

        recommendations = []

        for course in courses:

            score = self.score_course_for_talent(
                talent,
                course
            )

            if score <= 0:
                continue

            reason = self.get_course_recommendation_reason(
                talent,
                course
            )

            recommendations.append({
                "course": course,
                "score": score,
                "reason": reason,
            })

        recommendations.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return recommendations[:limit]


    def score_event_for_talent(self, talent, event):
        """
        Score how relevant an event is to a talent.
        """

        if not talent or not event:
            return 0

        score = 0

        user = talent.user

        # ==========================================
        # BASIC ELIGIBILITY
        # ==========================================

        if event.status != "PUBLISHED":
            return 0

        # Do not recommend events the talent
        # has already registered for.
        if event.registrations.filter(
            talent=talent
        ).exists():
            return 0

        # ==========================================
        # EVENT CATEGORY / DOMAIN MATCH
        # ==========================================

        if event.category and event.category.domain:

            event_domain_name = self.normalize_text(
                event.category.domain.name
            )

            for domain in talent.domains.all():

                talent_domain_name = self.normalize_text(
                    domain.name
                )

                if (
                    talent_domain_name in event_domain_name
                    or event_domain_name in talent_domain_name
                ):
                    score += 30
                    break

        # ==========================================
        # SKILL MATCH
        # ==========================================

        event_text = self.normalize_text(
            f"{event.title} {event.description}"
        )

        exact_skill_matches = 0

        for skill in talent.skills.all():

            skill_name = self.normalize_text(
                skill.name
            )

            if skill_name and skill_name in event_text:
                exact_skill_matches += 1

        score += min(
            exact_skill_matches * 10,
            25
        )

        # ==========================================
        # RELATED SKILLS
        # ==========================================

        related_skill_matches = 0

        for domain in talent.domains.all():

            related_skills = (
                self.get_related_skills_for_domains(
                    [domain]
                )
            )

            for related_skill in related_skills:

                related_name = self.normalize_text(
                    related_skill
                )

                if (
                    related_name
                    and related_name in event_text
                ):
                    related_skill_matches += 1

        score += min(
            related_skill_matches * 5,
            15
        )

        # ==========================================
        # EVENT TYPE
        # ==========================================

        if event.event_type in [
            "WORKSHOP",
            "BOOTCAMP",
            "CONFERENCE",
            "WEBINAR",
        ]:
            score += 5

        elif event.event_type in [
            "AUDITION",
            "TRIAL",
            "COMPETITION",
        ]:
            score += 3

        # ==========================================
        # ONLINE ACCESSIBILITY
        # ==========================================

        if event.online:
            score += 3

        # ==========================================
        # EVENT QUALITY
        # ==========================================

        feedback_count = event.feedback.count()

        if feedback_count >= 10:
            score += 5

        elif feedback_count >= 5:
            score += 3

        elif feedback_count >= 1:
            score += 1

        # ==========================================
        # RETURN FINAL SCORE
        # ==========================================

        return min(score, 100)


    def recommend_events_for_talent(self, talent, limit=10):
        """
        Return the most relevant published events
        for a talent.
        """

        if not talent:
            return []

        from events.models import Event

        events = Event.objects.filter(
            status="PUBLISHED"
        ).exclude(
            registrations__talent=talent
        ).distinct()

        recommendations = []

        for event in events:

            score = self.score_event_for_talent(
                talent,
                event
            )

            if score <= 0:
                continue

            reason = self.get_event_recommendation_reason(
                talent,
                event
            )

            recommendations.append({
                "event": event,
                "score": score,
                "reason": reason,
            })

        recommendations.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return recommendations[:limit]


    def get_event_recommendation_reason(self, talent, event):
        """
        Explain why an event is recommended to a talent.
        """

        reasons = []

        # ==========================================
        # DOMAIN MATCH
        # ==========================================

        if event.category and event.category.domain:

            event_domain_name = self.normalize_text(
                event.category.domain.name
            )

            for domain in talent.domains.all():

                talent_domain_name = self.normalize_text(
                    domain.name
                )

                if (
                    talent_domain_name in event_domain_name
                    or event_domain_name in talent_domain_name
                ):
                    reasons.append(
                        f"Matches your {domain.name} domain."
                    )
                    break

        # ==========================================
        # SKILL MATCH
        # ==========================================

        event_text = self.normalize_text(
            f"{event.title} {event.description}"
        )

        matched_skills = []

        for skill in talent.skills.all():

            skill_name = self.normalize_text(
                skill.name
            )

            if (
                skill_name
                and skill_name in event_text
            ):
                matched_skills.append(skill.name)

        if matched_skills:

            if len(matched_skills) == 1:

                reasons.append(
                    f"Matches your {matched_skills[0]} skill."
                )

            else:

                displayed_skills = matched_skills[:3]

                reasons.append(
                    "Matches your skills in "
                    + ", ".join(displayed_skills)
                    + "."
                )

        # ==========================================
        # EVENT TYPE
        # ==========================================

        event_type_labels = {
            "WORKSHOP": "workshop",
            "BOOTCAMP": "bootcamp",
            "CONFERENCE": "conference",
            "WEBINAR": "webinar",
            "COMPETITION": "competition",
            "AUDITION": "audition",
            "TRIAL": "talent trial",
        }

        event_type = event_type_labels.get(
            event.event_type
        )

        if event_type:
            reasons.append(
                f"This is a {event_type}."
            )

        # ==========================================
        # ONLINE
        # ==========================================

        if event.online:
            reasons.append(
                "This event is available online."
            )

        # ==========================================
        # FALLBACK
        # ==========================================

        if not reasons:
            reasons.append(
                "Recommended based on your profile."
            )

        return " ".join(reasons)

    @staticmethod
    def get_talent_relationships(talent):
        """
        Return known relationship signals around a talent.

        These signals describe interactions and organizational
        relationships. They do not automatically imply formal
        affiliation.
        """

        relationships = {
            "coaches": [],
            "scouts": [],
            "organizations": [],
        }

        # ============================================
        # COACH RELATIONSHIPS
        # ============================================

        try:

            coach_follows = talent.coached_by.select_related(
                "coach",
                "coach__user",
                "coach__organization",
            )

            for relationship in coach_follows:

                coach = relationship.coach

                relationships["coaches"].append({
                    "coach": coach,
                    "type": "FOLLOW",
                    "organization": coach.organization,
                })

        except Exception:
            pass


        # ============================================
        # SCOUT RELATIONSHIPS
        # ============================================

        try:

            scout_follows = talent.scout_followers.select_related(
                "scout",
                "scout__user",
                "scout__organization",
            )

            for relationship in scout_follows:

                scout = relationship.scout

                relationships["scouts"].append({
                    "scout": scout,
                    "type": "FOLLOW",
                    "organization": scout.organization,
                })

        except Exception:
            pass


        # ============================================
        # COACH VIEWS
        # ============================================

        try:

            coach_views = talent.coach_views.select_related(
                "coach",
                "coach__user",
                "coach__organization",
            )

            for relationship in coach_views:

                coach = relationship.coach

                relationships["coaches"].append({
                    "coach": coach,
                    "type": "VIEW",
                    "organization": coach.organization,
                })

        except Exception:
            pass


        # ============================================
        # SCOUT VIEWS
        # ============================================

        try:

            scout_views = talent.scout_views.select_related(
                "scout",
                "scout__user",
                "scout__organization",
            )

            for relationship in scout_views:

                scout = relationship.scout

                relationships["scouts"].append({
                    "scout": scout,
                    "type": "VIEW",
                    "organization": scout.organization,
                })

        except Exception:
            pass


        # ============================================
        # REMOVE DUPLICATES
        # ============================================

        for relationship_type in (
            "coaches",
            "scouts",
        ):

            unique = {}

            for relationship in relationships[
                relationship_type
            ]:

                person = relationship[
                    relationship_type[:-1]
                ]

                key = person.id

                if key not in unique:

                    unique[key] = relationship

                else:

                    # FOLLOW is stronger than VIEW
                    if relationship["type"] == "FOLLOW":

                        unique[key] = relationship

            relationships[
                relationship_type
            ] = list(unique.values())


        # ============================================
        # ORGANIZATIONS
        # ============================================

        organization_ids = set()

        for relationship in relationships["coaches"]:

            organization = relationship["organization"]

            if organization:
                organization_ids.add(
                    organization.id
                )

        for relationship in relationships["scouts"]:

            organization = relationship["organization"]

            if organization:
                organization_ids.add(
                    organization.id
                )

        relationships["organizations"] = list(
            organization_ids
        )

        return relationships



    @staticmethod
    def get_domain_skill_relevance(domain, skills):
        """
        Calculate how relevant a set of skills is to a specific domain.

        A talent may have multiple domains and multiple skills.
        The method therefore evaluates all supplied skills instead
        of assuming that a talent has only one specialization.
        """

        if not domain:
            return 0

        domain_name = (
            str(domain)
            .lower()
            .strip()
        )

        if not domain_name:
            return 0

        matched_skills = 0

        for skill in skills:

            skill_text = (
                str(skill)
                .lower()
                .strip()
            )

            if not skill_text:
                continue

            # Direct relationship:
            # Example:
            # domain = "Football"
            # skill  = "Football Coaching"
            if (
                domain_name in skill_text
                or skill_text in domain_name
            ):
                matched_skills += 1

        return matched_skills


    @staticmethod
    def get_related_skills_for_domain(domain):
        """
        Return skills whose category is related to the given talent domain.
        Supports categories such as:
            Football
            Football Technical Skills
            Football Physical Skills
            Football Tactical Skills
        """

        from skills.models import Skill

        domain_name = (domain.name or "").strip().lower()

        if not domain_name:
            return Skill.objects.none()

        return Skill.objects.filter(
            category__name__icontains=domain_name
        ).distinct()



    @staticmethod
    def normalize_text(value):
        """
        Normalize text before comparison.
        """
        if not value:
            return ""

        return str(value).strip().lower()


    @staticmethod
    def get_matching_domains(talent, text):
        """
        Return all talent domains that match a supplied piece of text.
        A talent may have multiple domains.
        """

        search_text = RecommendationEngine.normalize_text(text)

        if not search_text:
            return []

        matching_domains = []

        for domain in talent.domains.all():

            domain_name = RecommendationEngine.normalize_text(
                domain.name
            )

            if (
                search_text in domain_name
                or domain_name in search_text
            ):
                matching_domains.append(domain)

        return matching_domains



    @staticmethod
    def get_related_skills_for_domains(domains):
        """
        Return skill names that are related to skills
        associated with the supplied talent domains.

        Uses the existing SkillRelationship model while
        supporting domain-specific SkillCategory names.
        """

        from skills.models import Skill, SkillRelationship

        related_skill_names = set()

        if not domains:
            return related_skill_names

        domain_names = {
            RecommendationEngine.normalize_text(domain.name)
            for domain in domains
            if domain.name
        }

        domain_names.discard("")

        if not domain_names:
            return related_skill_names

        domain_skills = Skill.objects.none()

        for domain_name in domain_names:
            domain_skills = domain_skills | Skill.objects.filter(
                category__name__icontains=domain_name
            )

        relationships = SkillRelationship.objects.filter(
            skill__in=domain_skills
        ).select_related(
            "related_skill"
        )

        related_skill_names.update(
            relationship.related_skill.name.strip().lower()
            for relationship in relationships
            if relationship.related_skill.name
        )

        return related_skill_names


    @staticmethod
    def get_related_skill_matches(source_talent, candidate):
        """
        Find candidate skills that are related to the source
        talent's skills.

        Returns:
            A list of dictionaries containing:
            - source_skill
            - related_skill
            - strength
        """

        from skills.models import SkillRelationship

        if not source_talent or not candidate:
            return []

        source_skill_ids = source_talent.skills.values_list(
            "id",
            flat=True
        )

        candidate_skill_ids = set(
            candidate.skills.values_list(
                "id",
                flat=True
            )
        )

        if not source_skill_ids or not candidate_skill_ids:
            return []

        relationships = SkillRelationship.objects.filter(
            skill_id__in=source_skill_ids,
            related_skill_id__in=candidate_skill_ids
        ).select_related(
            "skill",
            "related_skill"
        )

        return [
            {
                "source_skill": relationship.skill,
                "related_skill": relationship.related_skill,
                "strength": float(relationship.strength),
            }
            for relationship in relationships
        ]

    @staticmethod
    def get_related_skill_matches_for_role_model(
        talent,
        role_model
    ):
        """
        Find directional skill relationships between
        the talent's skills and the role model's skills.

        The relationship direction is:

            talent skill → role model skill

        Only actual SkillRelationship records are considered.
        """

        from skills.models import SkillRelationship

        talent_skills = talent.skills.all()
        role_model_skills = role_model.skills.all()

        talent_skill_ids = set(
            talent_skills.values_list(
                "id",
                flat=True
            )
        )

        role_model_skill_ids = set(
            role_model_skills.values_list(
                "id",
                flat=True
            )
        )

        if not talent_skill_ids or not role_model_skill_ids:
            return []

        relationships = (
            SkillRelationship.objects
            .filter(
                skill_id__in=talent_skill_ids,
                related_skill_id__in=role_model_skill_ids
            )
            .select_related(
                "skill",
                "related_skill"
            )
            .order_by(
                "-strength"
            )
        )

        matches = []

        for relationship in relationships:

            matches.append({
                "talent_skill": relationship.skill,
                "role_model_skill": relationship.related_skill,
                "strength": float(
                    relationship.strength
                ),
            })

        return matches


    @staticmethod
    def get_matching_skills(talent, skill_names):
        """
        Return the talent's skills that match a supplied
        collection of skill names.
        """

        normalized_names = {
            RecommendationEngine.normalize_text(name)
            for name in skill_names
            if name
        }

        matches = []

        for skill in talent.skills.all():

            skill_name = RecommendationEngine.normalize_text(
                skill.name
            )

            if skill_name in normalized_names:
                matches.append(skill)

        return matches


    @staticmethod
    def score_talent_for_scout(scout, talent):
        """
        Calculate how relevant a specific talent is to a specific scout.

        A talent can have multiple domains and skills, so the scorer
        considers all of them rather than assuming one specialization.
        """

        score = 0

        scout_profile = scout

        if not scout_profile:
            return 0

        # ============================================
        # ORGANIZATION MATCH
        # ============================================

        if scout_profile.organization:

            if talent.experiences.filter(
                company__icontains=scout_profile.organization.name
            ).exists():

                score += 15

        # ============================================
        # SPECIALIZATION MATCH
        # ============================================

        if scout_profile.specialization:

            specialization = (
                scout_profile.specialization
                .strip()
                .lower()
            )

            # ----------------------------------------
            # DOMAIN MATCH
            # ----------------------------------------

            matching_domains = (
                RecommendationEngine.get_matching_domains(
                    talent,
                    specialization
                )
            )

            if matching_domains:

                score += 20

            # ----------------------------------------
            # RELATED SKILLS FROM MATCHING DOMAINS
            # ----------------------------------------

            if matching_domains:

                related_skill_names = (
                    RecommendationEngine
                    .get_related_skills_for_domains(
                        matching_domains
                    )
                )

                related_skill_matches = (
                    RecommendationEngine
                    .get_matching_skills(
                        talent,
                        related_skill_names
                    )
                )

                score += min(
                    len(related_skill_matches) * 3,
                    15
                )

            # ----------------------------------------
            # DIRECT SKILL MATCH
            # ----------------------------------------

            matching_skills = 0

            for skill in talent.skills.all():

                skill_text = (
                    skill.name
                    .strip()
                    .lower()
                )

                if (
                    specialization in skill_text
                    or skill_text in specialization
                ):
                    matching_skills += 1

            score += min(
                matching_skills * 5,
                15
            )

        # ============================================
        # LOCATION MATCH
        # ============================================

        if (
            scout_profile.country
            and talent.country
            and scout_profile.country.strip().lower()
            == talent.country.strip().lower()
        ):
            score += 10

        if (
            scout_profile.city
            and talent.city
            and scout_profile.city.strip().lower()
            == talent.city.strip().lower()
        ):
            score += 5

        # ============================================
        # PREVIOUS INTERACTION
        # ============================================

        if ScoutTalentView.objects.filter(
            scout=scout_profile,
            talent=talent
        ).exists():

            score += 10

        if ScoutTalentFollow.objects.filter(
            scout=scout_profile,
            talent=talent
        ).exists():

            score += 20

        if ScoutTalentBookmark.objects.filter(
            scout=scout_profile,
            talent=talent
        ).exists():

            score += 25

        # ============================================
        # TALENT QUALITY
        # ============================================

        if talent.verified:
            score += 10

        if talent.is_role_model:
            score += 5

        # ============================================
        # EXPERIENCE
        # ============================================

        score += min(
            talent.experiences.count() * 2,
            10
        )

        # ============================================
        # PROFILE STRENGTH
        # ============================================

        strength = ProfileStrengthService.calculate_strength(
            talent
        )

        score += (
            strength / 100
        ) * 5

        return round(
            score,
            2
        )

    @staticmethod
    def score_talent_for_coach(coach, talent):
        """
        Calculate how relevant a specific talent is to a specific coach.

        A talent can have multiple domains and skills, so the scorer
        considers all of them rather than assuming one specialization.
        """

        score = 0

        coach_profile = coach

        if not coach_profile:
            return 0

        # ============================================
        # ORGANIZATION MATCH
        # ============================================

        if coach_profile.organization:

            if talent.experiences.filter(
                company__icontains=coach_profile.organization.name
            ).exists():

                score += 15

        # ============================================
        # SPECIALIZATION MATCH
        # ============================================

        if coach_profile.specialization:

            specialization = (
                coach_profile.specialization
                .strip()
                .lower()
            )

            # ----------------------------------------
            # DOMAIN MATCH
            # ----------------------------------------

            matching_domains = (
                RecommendationEngine.get_matching_domains(
                    talent,
                    specialization
                )
            )

            if matching_domains:

                score += 20

            # ----------------------------------------
            # RELATED SKILLS FROM MATCHING DOMAINS
            # ----------------------------------------

            if matching_domains:

                related_skill_names = (
                    RecommendationEngine
                    .get_related_skills_for_domains(
                        matching_domains
                    )
                )

                related_skill_matches = (
                    RecommendationEngine
                    .get_matching_skills(
                        talent,
                        related_skill_names
                    )
                )

                score += min(
                    len(related_skill_matches) * 3,
                    15
                )

            # ----------------------------------------
            # DIRECT SKILL MATCH
            # ----------------------------------------

            matching_skills = 0

            for skill in talent.skills.all():

                skill_text = (
                    skill.name
                    .strip()
                    .lower()
                )

                if (
                    specialization in skill_text
                    or skill_text in specialization
                ):
                    matching_skills += 1

            score += min(
                matching_skills * 5,
                15
            )

        # ============================================
        # LOCATION MATCH
        # ============================================

        if (
            coach_profile.country
            and talent.country
            and coach_profile.country.strip().lower()
            == talent.country.strip().lower()
        ):
            score += 10

        if (
            coach_profile.city
            and talent.city
            and coach_profile.city.strip().lower()
            == talent.city.strip().lower()
        ):
            score += 5

        # ============================================
        # PREVIOUS INTERACTION
        # ============================================

        if CoachTalentView.objects.filter(
            coach=coach_profile,
            talent=talent
        ).exists():

            score += 10

        if CoachTalentFollow.objects.filter(
            coach=coach_profile,
            talent=talent
        ).exists():

            score += 20

        if CoachTalentBookmark.objects.filter(
            coach=coach_profile,
            talent=talent
        ).exists():

            score += 25

        # ============================================
        # TALENT QUALITY
        # ============================================

        if talent.verified:
            score += 10

        if talent.is_role_model:
            score += 5

        # ============================================
        # EXPERIENCE
        # ============================================

        score += min(
            talent.experiences.count() * 2,
            10
        )

        # ============================================
        # PROFILE STRENGTH
        # ============================================

        strength = ProfileStrengthService.calculate_strength(
            talent
        )

        score += (
            strength / 100
        ) * 5

        return round(
            score,
            2
        )

    @staticmethod
    def recommend_coaches_for_talent(talent, limit=10):
        """
        Recommend the most relevant coaches for a specific talent.

        A talent can have multiple domains and skills. Each coach
        is therefore scored against the talent as a whole.
        """

        from coaches.models import CoachProfile

        coaches = CoachProfile.objects.select_related(
            "user",
            "organization",
            "sport",
        ).all()

        recommendations = []

        for coach in coaches:

            # Do not recommend the talent's own account
            if coach.user_id == talent.user_id:
                continue

            score = RecommendationEngine.score_talent_for_coach(
                coach,
                talent
            )

            coach.recommendation_score = score

            recommendations.append(coach)

        recommendations.sort(
            key=lambda coach: (
                coach.recommendation_score,
                coach.created_at
            ),
            reverse=True
        )

        return recommendations[:limit]



    @staticmethod
    def explain_match(talent, opportunity):


        reasons = []



        # Domain


        if opportunity.domain:


            if talent.domains.filter(

                id=opportunity.domain.id

            ).exists():


                reasons.append(

                    f"{opportunity.domain.name} domain match"

                )





        # Skills


        matched_skills = talent.skills.filter(

            id__in=opportunity.skills.values_list(

                "id",

                flat=True

            )

        )



        if matched_skills.exists():


            skills = ", ".join(

                matched_skills.values_list(

                    "name",

                    flat=True

                )

            )


            reasons.append(

                f"Matched skills: {skills}"

            )





        # Verification


        if talent.verified:


            reasons.append(

                "Verified talent"

            )





        # Portfolio


        if talent.portfolio_items.exists():


            reasons.append(

                "Portfolio available"

            )





        # Experience


        if talent.experiences.exists():


            reasons.append(

                "Relevant experience"

            )



        return reasons







    @staticmethod
    def recommend_talents(opportunity):


        candidates = RecommendationEngine.get_candidates(

            opportunity

        )



        results = []



        for talent in candidates:


            results.append(

                {

                    "talent": talent,

                    "score":

                    RecommendationEngine.calculate_score(

                        talent,

                        opportunity

                    ),


                    "reasons":

                    RecommendationEngine.explain_match(

                        talent,

                        opportunity

                    )

                }

            )




        results.sort(

            key=lambda x:x["score"],

            reverse=True

        )



        return results[:10]


    # =====================================================
    # GENERATE ORGANIZATION RECOMMENDATIONS
    # =====================================================

    @staticmethod
    def generate_for_organization(opportunity):

        organization = opportunity.organization

        # =============================================
        # REMOVE PREVIOUS RECOMMENDATIONS
        # FOR THIS OPPORTUNITY
        # =============================================

        RecommendationHistory.objects.filter(
            organization=organization,
            opportunity=opportunity
        ).delete()

        # =============================================
        # GENERATE FRESH RECOMMENDATIONS
        # =============================================

        results = RecommendationEngine.recommend_talents(
            opportunity
        )

        generated = []

        for result in results:

            talent = result["talent"]
            score = result["score"]

            recommendation = RecommendationHistory.objects.create(
                organization=organization,
                talent=talent,
                opportunity=opportunity,
                score=score
            )

            generated.append(
                recommendation
            )

        return generated


    @staticmethod
    def recommend_organizations_for_user(user, limit=10):
        """
        Recommend the most relevant organizations for a user.
        """

        from organizations.models import Organization

        if not user:
            return []

        organizations = Organization.objects.all()

        recommendations = []

        for organization in organizations:

            score = (
                RecommendationEngine
                .score_organization_for_user(
                    user,
                    organization
                )
            )

            if score <= 0:
                continue

            recommendations.append({
                "organization": organization,
                "score": score,
            })

        recommendations.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return recommendations[:limit]

    @staticmethod
    def recommend_opportunities_for_user(user, limit=10):
        """
        Recommend the most relevant active opportunities for a user.
        """

        from opportunities.models import Opportunity

        if not user:
            return []

        opportunities = Opportunity.objects.filter(
            active=True
        ).select_related(
            "organization"
        )

        recommendations = []

        for opportunity in opportunities:

            score = (
                RecommendationEngine
                .score_opportunity_for_user(
                    user,
                    opportunity
                )
            )

            if score <= 0:
                continue

            recommendations.append({
                "opportunity": opportunity,
                "score": score,
            })

        recommendations.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return recommendations[:limit]
