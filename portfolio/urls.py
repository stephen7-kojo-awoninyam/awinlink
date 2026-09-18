from django.urls import path

from . import views



urlpatterns = [

    path(

        "add/",

        views.add_portfolio_item,

        name="add_portfolio_item"

    ),
        path(
        "",
        views.portfolio_list,
        name="portfolio_list"
    ),


    path(
        "edit/<int:item_id>/",
        views.edit_portfolio_item,
        name="edit_portfolio_item"
    ),


    path(
        "delete/<int:item_id>/",
        views.delete_portfolio_item,
        name="delete_portfolio_item"
    ),

]