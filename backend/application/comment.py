from flask import Blueprint, jsonify, request
from .tools import token_to_user
from uuid import uuid4
from .postgres import db_close, db_open
from .log import log

bp = Blueprint("comment", __name__)


@bp.get("/comment/<key>")
def get_comments(key, cur=None):
    close_conn = not cur
    if not cur:
        con, cur = db_open()

    user = token_to_user(cur)
    if not user:
        if close_conn:
            db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid token"
        })

    order = "latest"
    status = "active"
    if "order" in request.args:
        order = request.args["order"]
    if (
        "comment:view_deleted" in user["permissions"]
        and "status" in request.args
    ):
        status = request.args["status"]

    # likes, like, dislike, ratings, rating_count
    order_by = {
        'latest': 'log.date',
        'oldest': 'log.date',
        'high_rating': 'feedback.rating',
        'low_rating': 'feedback.rating',
        'name (a-z)': '"user".name',
        'name (z-a)': '"user".name'
    }

    order_dir = {
        'latest': 'DESC',
        'oldest': 'ASC',
        'high_rating': 'DESC',
        'low_rating': 'ASC',
        'name (a-z)': 'ASC',
        'name (z-a)': 'DESC'
    }

    cur.execute("""
        SELECT
            comment.key,
            comment.comment,
            comment.path,
            comment."like",
            comment.dislike,
            log.date,
            jsonb_build_object(
                'key', "user".key,
                'name', "user".name,
                'photo', "user".photo
            ) AS user

        FROM comment
        LEFT JOIN "user" ON comment.user_key = "user".key
        LEFT JOIN log ON
            comment.key = log.entity_key
            AND log.action = 'created'
            AND log.entity_type = 'comment'
        WHERE
            comment.post_key = %s
            AND comment.status = %s
        ORDER BY {} {};
    """.format(
        order_by[order],
        order_dir[order]
    ), (
        key,
        status
    ))
    comments = cur.fetchall()
    for x in comments:
        x["user"]["photo"] = f"{request.host_url}photo/{x[
            "user"]["photo"]}" if x["user"]["photo"] else None

    if close_conn:
        db_close(con, cur)
    return jsonify({
        "status": 200,
        "comments": comments,
        "order_by": list(order_by.keys()),
        "_status": ["active", "deleted"]
    })


@bp.post("/comment/<key>")
def create(key):
    con, cur = db_open()

    user = token_to_user(cur)
    if not user or not user["login"]:
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid token"
        })

    cur.execute("""
        SELECT * FROM post WHERE slug = %s OR key = %s;
    """, (key, key))
    post = cur.fetchone()

    if (
        not post
        or "path" not in request.json
        or type(request.json["path"]) is not list
    ):
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid request"
        })

    if "comment" not in request.json or not request.json["comment"]:
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "comment": "cannot be empty"
        })

    cur.execute("""
        SELECT * FROM comment WHERE key = ANY(%s);
    """, (request.json["path"],))
    comments = cur.fetchall()
    if len(comments) != len(request.json["path"]):
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid request"
        })

    cur.execute("""
        INSERT INTO comment (key, user_key, post_key, comment, path)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *;
    """, (
        uuid4().hex,
        user["key"],
        post["key"],
        request.json["comment"],
        request.json["path"]
    ))
    comment = cur.fetchone()

    log(
        cur=cur,
        user_key=user["key"],
        action="created",
        entity_key=comment["key"],
        entity_type="comment",
        misc={
            "post_key": post["key"]
        }
    )

    comments = get_comments(post["key"], cur)
    db_close(con, cur)
    return comments


@bp.post("/comment/like/<key>")
def like(key):
    con, cur = db_open()

    user = token_to_user(cur)
    if not user:
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid token"
        })

    cur.execute("""
        SELECT
            comment.key,
            comment.comment,
            comment.path,
            comment."like",
            comment.dislike,
            log.date,
            jsonb_build_object(
                'key', "user".key,
                'name', "user".name,
                'photo', "user".photo
            ) AS user

        FROM comment
        LEFT JOIN log ON comment.key = log.entity_key
        LEFT JOIN "user" ON comment.user_key = "user".key
        WHERE comment.key = %s;
    """, (key,))
    comment = cur.fetchone()

    if (
        not comment
        or "like" not in request.json
        or type(request.json["like"]) is not bool
    ):
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid request"
        })

    comment["user"]["photo"] = f"{request.host_url}photo/{comment[
        "user"]["photo"]}" if comment["user"]["photo"] else None

    if request.json["like"]:
        if user["key"] in comment["dislike"]:
            comment["dislike"].remove(user["key"])
        if user["key"] in comment["like"]:
            comment["like"].remove(user["key"])
        else:
            comment["like"].append(user["key"])
    else:
        if user["key"] in comment["like"]:
            comment["like"].remove(user["key"])
        if user["key"] in comment["dislike"]:
            comment["dislike"].remove(user["key"])
        else:
            comment["dislike"].append(user["key"])

    cur.execute("""
        UPDATE comment
        SET
            "like" = %s,
            dislike = %s
        WHERE key = %s;
    """, (
        comment["like"],
        comment["dislike"],
        comment["key"]
    ))

    log(
        cur=cur,
        user_key=user["key"],
        action='liked' if request.json['like'] else 'disliked',
        entity_key=comment["key"],
        entity_type="comment",
        misc={
            "post_key": comment["post_key"]
        }
    )

    db_close(con, cur)
    return jsonify({
        "status": 200,
        "comment": comment
    })


@ bp.delete("/comment/<key>")
def delete(key):
    con, cur = db_open()

    user = token_to_user(cur)
    if not user:
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid token"
        })

    cur.execute("""
        SELECT * FROM comment WHERE key = %s AND user_key = %s;
    """, (key, user["key"]))
    comment = cur.fetchone()

    if not comment:
        db_close(con, cur)
        return jsonify({
            "status": 400,
            "error": "invalid request"
        })

    cur.execute("""
        UPDATE comment
        SET status = 'deleted'
        WHERE
            key = %s
            OR %s = ANY(path);
    """, (
        comment["key"],
        comment["key"]
    ))

    log(
        cur=cur,
        user_key=user["key"],
        action="deleted",
        entity_key=comment["key"],
        entity_type="comment",
        misc={
            "post_key": comment["post_key"]
        }
    )

    comments = get_comments(comment["post_key"], cur)
    db_close(con, cur)
    return comments
